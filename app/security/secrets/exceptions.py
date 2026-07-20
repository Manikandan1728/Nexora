"""
app/security/secrets/exceptions.py — Typed secret-store exceptions.

[ADDITIVE] Phase 3. No existing exception hierarchy is modified.
These are standalone exceptions — not subclasses of NexoraAPIError —
because the secret store is a generic infrastructure layer, not API-specific.
They are wrapped into appropriate API errors at the route layer if they
ever reach an API boundary.

Security invariant: no exception message contains plaintext secrets,
raw key material, nonces, or authentication tags.
"""
from __future__ import annotations


class SecretStoreError(Exception):
    """Base class for all secret-store errors."""
    def __init__(self, message: str, *, safe_detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        # safe_detail may be logged; must never contain plaintext or key material
        self.safe_detail = safe_detail or ""


class SecretStoreConfigurationError(SecretStoreError):
    """Missing or malformed configuration (key, provider, version)."""


class SecretStoreUnavailableError(SecretStoreError):
    """Store backend cannot be reached or initialized."""


class SecretEncryptionError(SecretStoreError):
    """Encryption operation failed."""


class SecretDecryptionError(SecretStoreError):
    """Decryption failed — includes wrong key, wrong context, or integrity failure."""


class SecretIntegrityError(SecretDecryptionError):
    """Ciphertext failed authentication (tampered, wrong context, or wrong key)."""


class SecretPayloadFormatError(SecretDecryptionError):
    """Payload string is malformed, has unsupported version, or missing fields."""


class SecretKeyNotFoundError(SecretDecryptionError):
    """The key_id referenced in the payload is not in the key registry."""


class SecretDeletionError(SecretStoreError):
    """Deletion operation failed."""
