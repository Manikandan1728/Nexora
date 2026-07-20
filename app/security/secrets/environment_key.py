"""
app/security/secrets/environment_key.py — AES-256-GCM secret store.

[ADDITIVE] Phase 8.

Algorithm: AES-256-GCM (DR-S1).
Nonce: 96-bit (12 bytes), cryptographically random per encryption.
Key: 256-bit (32 bytes), base64url-encoded, injected via constructor.
Context: UTF-8 encoded as AAD (DR-S4).
Payload format: nexora:v1:<base64(json)> (DR-S3).
Empty plaintext: rejected (DR-S6).
"""
from __future__ import annotations

import logging
import secrets as _secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.security.secrets.base import SecretStore, SecretStoreHealth, SecretStoreStatus
from app.security.secrets.exceptions import (
    SecretEncryptionError, SecretDecryptionError,
    SecretIntegrityError, SecretKeyNotFoundError,
)
from app.security.secrets.models import EncryptedPayload
from app.security.secrets.validation import decode_and_validate_key

logger = logging.getLogger(__name__)

_ALGORITHM = "AES-256-GCM"
_ENCRYPTION_VERSION = "v1"
_NONCE_BYTES = 12


class EnvironmentKeySecretStore:
    """
    AES-256-GCM secret store backed by an environment-provided key.

    Key registry supports multiple key_ids (DR-S3) for future rotation.
    Currently one active key_id is used for encryption; all registered
    key_ids can be used for decryption.

    delete() is a documented no-op: ciphertext is inline in the database
    field; deleting the DB column value removes the secret.
    """

    def __init__(
        self,
        key_bytes: bytes,
        key_id: str,
        extra_keys: dict[str, bytes] | None = None,
    ) -> None:
        """
        Args:
            key_bytes:   Validated 32-byte AES-256 key for encryption.
            key_id:      Identifier for this key (stored in payload).
            extra_keys:  Additional {key_id: key_bytes} for decryption only.
                         Never logged. Used for rotation support (DR-S3).
        """
        self._active_key_id = key_id
        # Build registry: active key + any extra decryption keys
        self._key_registry: dict[str, AESGCM] = {
            key_id: AESGCM(key_bytes),
        }
        if extra_keys:
            for kid, kb in extra_keys.items():
                self._key_registry[kid] = AESGCM(kb)
        self._version = _ENCRYPTION_VERSION
        # Safe repr — never includes key material
        logger.debug(
            "EnvironmentKeySecretStore initialized: key_id=%r version=%s keys=%d",
            key_id, _ENCRYPTION_VERSION, len(self._key_registry),
        )

    @classmethod
    def from_env(
        cls,
        raw_key: str | None,
        key_id: str,
        extra_keys: dict[str, bytes] | None = None,
    ) -> "EnvironmentKeySecretStore":
        """Construct from a raw base64url-encoded key string (DR-S2 fail-fast)."""
        key_bytes = decode_and_validate_key(raw_key)
        return cls(key_bytes=key_bytes, key_id=key_id, extra_keys=extra_keys)

    # ------------------------------------------------------------------
    # SecretStore protocol
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: str, *, context: str | None = None) -> str:
        """
        Encrypt plaintext with AES-256-GCM.

        DR-S6: empty/whitespace plaintext raises SecretEncryptionError.
        DR-S4: context is encoded as UTF-8 AAD. None → b"" AAD.
        Returns: nexora:v1:<base64(json)> token.
        """
        if not plaintext or not plaintext.strip():
            raise SecretEncryptionError(
                "Plaintext must not be empty or whitespace-only.",
                safe_detail="empty_plaintext",
            )
        aad = _encode_context(context)
        nonce = _secrets.token_bytes(_NONCE_BYTES)
        try:
            aesgcm = self._key_registry[self._active_key_id]
            ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        except Exception as exc:
            raise SecretEncryptionError(
                "Encryption failed.", safe_detail=f"encrypt_error:{type(exc).__name__}"
            ) from exc

        payload = EncryptedPayload(
            version=self._version,
            algorithm=_ALGORITHM,
            key_id=self._active_key_id,
            nonce=nonce,
            ciphertext=ciphertext_with_tag,
        )
        token = payload.serialize()
        logger.debug(
            "SecretStore.encrypt: key_id=%r version=%s context_present=%s",
            self._active_key_id, self._version, context is not None,
        )
        return token

    def decrypt(self, ciphertext: str, *, context: str | None = None) -> str:
        """
        Decrypt a nexora:v1:... token.

        DR-S4: context must match exactly.
        Raises SecretIntegrityError on tamper, wrong context, wrong key.
        Raises SecretKeyNotFoundError if key_id not in registry.
        """
        payload = EncryptedPayload.deserialize(ciphertext)
        aad = _encode_context(context)

        aesgcm = self._key_registry.get(payload.key_id)
        if aesgcm is None:
            raise SecretKeyNotFoundError(
                f"Key ID {payload.key_id!r} not found in registry.",
                safe_detail=f"unknown_key_id:{payload.key_id}",
            )
        try:
            plaintext_bytes = aesgcm.decrypt(payload.nonce, payload.ciphertext, aad)
        except Exception as exc:
            raise SecretIntegrityError(
                "Decryption failed: payload may be tampered, key incorrect, "
                "or context mismatch.",
                safe_detail=f"decrypt_error:{type(exc).__name__}",
            ) from exc

        logger.debug(
            "SecretStore.decrypt: key_id=%r context_present=%s",
            payload.key_id, context is not None,
        )
        return plaintext_bytes.decode("utf-8")

    def delete(self, secret_reference: str) -> None:
        """
        No-op for inline-ciphertext store.

        The ciphertext is stored inline in the database field. Deleting the
        database field (setting it to NULL) removes the secret. This method
        exists to satisfy the protocol; callers should clear the DB column.
        """
        logger.debug("SecretStore.delete: no-op for inline-ciphertext store")

    def health_check(self) -> SecretStoreHealth:
        """Return safe health information — no key material exposed."""
        try:
            token = self.encrypt("_health_probe_", context="health_check")
            self.decrypt(token, context="health_check")
            status = SecretStoreStatus.HEALTHY
            msg = None
        except Exception as exc:
            status = SecretStoreStatus.DEGRADED
            msg = f"Health probe failed: {type(exc).__name__}"
        return SecretStoreHealth(
            status=status,
            provider="environment",
            encryption_version=self._version,
            key_id=self._active_key_id,
            message=msg,
        )


def _encode_context(context: str | None) -> bytes:
    """Encode context string to AAD bytes. None → b'' (DR-S4)."""
    if context is None:
        return b""
    return context.encode("utf-8")
