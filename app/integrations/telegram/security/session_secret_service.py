"""
app/integrations/telegram/security/session_secret_service.py

[ADDITIVE] Part 2C — Phase 2

Dedicated encryption/decryption service for Telegram session secrets.
This is the only class authorized to read or write session-related AES-GCM
ciphertexts. It delegates to SecretStore but enforces strict context binding
so that ciphertexts cannot be replayed across different secret categories.
"""

from app.security.secrets.base import SecretStore
from app.integrations.telegram.security.session_contexts import (
    TELEGRAM_SESSION_REFERENCE_CONTEXT,
    TELEGRAM_TDLIB_DATABASE_KEY_CONTEXT,
    TELEGRAM_TDLIB_FILES_DATABASE_KEY_CONTEXT,
    TELEGRAM_SESSION_LOCATOR_CONTEXT,
    TELEGRAM_MTPROTO_SESSION_CONTEXT,
)
from app.integrations.telegram.security.session_errors import (
    TelegramSessionEncryptionError,
    TelegramSessionDecryptionError,
)
from app.integrations.telegram.models.session_models import (
    EncryptedTelegramSessionBundle,
    TelegramSessionValidationResult,
    TelegramSessionStatus,
)


class TelegramSessionSecretService:
    """
    Encrypts and decrypts Telegram session secrets using strict context bounds.
    """

    # V1 ciphertext prefix used by Nexora SecretStore
    _PREFIX = "nexora:v1:"

    def __init__(self, secret_store: SecretStore) -> None:
        self._store = secret_store

    def is_encrypted_payload(self, value: str) -> bool:
        """Return True if the payload appears to be an encrypted v1 payload."""
        return bool(value) and value.startswith(self._PREFIX)

    def _encrypt(self, value: str, context: str) -> str:
        if not value:
            raise TelegramSessionEncryptionError("Cannot encrypt an empty string.")
        if self.is_encrypted_payload(value):
            raise TelegramSessionEncryptionError("Double-encryption is prevented.")
        
        try:
            return self._store.encrypt(value, context=context)
        except Exception as e:
            raise TelegramSessionEncryptionError(f"Encryption failed: {e}") from e

    def _decrypt(self, ciphertext: str, context: str) -> str:
        if not ciphertext:
            raise TelegramSessionDecryptionError("Cannot decrypt an empty string.")
        if not self.is_encrypted_payload(ciphertext):
            raise TelegramSessionDecryptionError("Value is not an encrypted payload.")
        
        try:
            return self._store.decrypt(ciphertext, context=context)
        except Exception as e:
            raise TelegramSessionDecryptionError(f"Decryption failed: {e}") from e

    # -----------------------------------------------------------------------
    # Typed Field Operations
    # -----------------------------------------------------------------------

    def encrypt_session_reference(self, value: str) -> str:
        return self._encrypt(value, TELEGRAM_SESSION_REFERENCE_CONTEXT)

    def decrypt_session_reference(self, ciphertext: str) -> str:
        return self._decrypt(ciphertext, TELEGRAM_SESSION_REFERENCE_CONTEXT)

    def encrypt_tdlib_database_key(self, value: str) -> str:
        return self._encrypt(value, TELEGRAM_TDLIB_DATABASE_KEY_CONTEXT)

    def decrypt_tdlib_database_key(self, ciphertext: str) -> str:
        return self._decrypt(ciphertext, TELEGRAM_TDLIB_DATABASE_KEY_CONTEXT)

    def encrypt_tdlib_files_database_key(self, value: str) -> str:
        return self._encrypt(value, TELEGRAM_TDLIB_FILES_DATABASE_KEY_CONTEXT)

    def decrypt_tdlib_files_database_key(self, ciphertext: str) -> str:
        return self._decrypt(ciphertext, TELEGRAM_TDLIB_FILES_DATABASE_KEY_CONTEXT)

    def encrypt_session_locator(self, value: str) -> str:
        return self._encrypt(value, TELEGRAM_SESSION_LOCATOR_CONTEXT)

    def decrypt_session_locator(self, ciphertext: str) -> str:
        return self._decrypt(ciphertext, TELEGRAM_SESSION_LOCATOR_CONTEXT)

    def encrypt_telethon_session(self, value: str) -> str:
        return self._encrypt(value, TELEGRAM_MTPROTO_SESSION_CONTEXT)

    def decrypt_telethon_session(self, ciphertext: str) -> str:
        return self._decrypt(ciphertext, TELEGRAM_MTPROTO_SESSION_CONTEXT)

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    def validate_session_bundle(
        self, bundle: EncryptedTelegramSessionBundle
    ) -> TelegramSessionValidationResult:
        """
        Validates the encrypted bundle's structural integrity.
        (Does not perform a decrypt test).
        """
        has_ref = bool(bundle.session_reference_encrypted)
        has_db = bool(bundle.tdlib_database_key_encrypted)
        has_files_db = bool(bundle.tdlib_files_database_key_encrypted)

        # Basic validation rule: if we have anything, we expect at least the session reference.
        # This will be refined as actual TDLib logic dictates required combos.
        if not has_ref and not has_db and not has_files_db:
            status = TelegramSessionStatus.ABSENT
        elif has_ref:
            status = TelegramSessionStatus.AVAILABLE
        else:
            status = TelegramSessionStatus.PARTIAL

        return TelegramSessionValidationResult(
            status=status,
            has_session_reference=has_ref,
            has_database_key=has_db,
            has_files_database_key=has_files_db,
            error_code=None,
        )
