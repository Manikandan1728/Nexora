"""
app/security/secrets/in_memory.py — In-memory secret store for testing.

[ADDITIVE] Phase 9. DR-S5: Option A — real AES-256-GCM encryption with a
fixed deterministic test key.

Tests using this store exercise the same crypto code path as production
(tamper detection, format validation, context binding, round-trips).
The test key is a fixed 32-byte value — NEVER a valid production key.

Never set NEXORA_SECRET_STORE_PROVIDER=memory in production.
"""
from __future__ import annotations

import logging
from app.security.secrets.base import SecretStoreHealth, SecretStoreStatus
from app.security.secrets.environment_key import EnvironmentKeySecretStore
from app.security.secrets.exceptions import SecretDeletionError, SecretDecryptionError

logger = logging.getLogger(__name__)

# Fixed test key: 32 zero bytes. Documented as non-production only.
_TEST_KEY = b"\x00" * 32
_TEST_KEY_ID = "test-key-0"


class InMemorySecretStore:
    """
    In-memory secret store backed by real AES-256-GCM encryption (DR-S5 Option A).

    Wraps EnvironmentKeySecretStore with a fixed test key.
    Supports reference-level deletion: deleted references cannot be decrypted.
    Each instance is isolated — use fresh instances per test.

    NEVER activate this store in production.
    """

    def __init__(self) -> None:
        self._store = EnvironmentKeySecretStore(
            key_bytes=_TEST_KEY, key_id=_TEST_KEY_ID
        )
        self._deleted: set[str] = set()

    def encrypt(self, plaintext: str, *, context: str | None = None) -> str:
        token = self._store.encrypt(plaintext, context=context)
        logger.debug("InMemorySecretStore.encrypt: context_present=%s", context is not None)
        return token

    def decrypt(self, ciphertext: str, *, context: str | None = None) -> str:
        if ciphertext in self._deleted:
            raise SecretDecryptionError(
                "Secret has been deleted and cannot be decrypted.",
                safe_detail="deleted_reference",
            )
        return self._store.decrypt(ciphertext, context=context)

    def delete(self, secret_reference: str) -> None:
        """Mark reference as deleted. Idempotent."""
        self._deleted.add(secret_reference)
        logger.debug("InMemorySecretStore.delete: reference marked deleted")

    def health_check(self) -> SecretStoreHealth:
        return SecretStoreHealth(
            status=SecretStoreStatus.HEALTHY,
            provider="memory",
            encryption_version="v1",
            key_id=_TEST_KEY_ID,
            message="In-memory test store (not for production use)",
        )
