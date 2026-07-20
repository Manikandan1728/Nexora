"""
app/integrations/telegram/security/session_errors.py

[ADDITIVE] Part 2C — Typed Session Errors
Typed exceptions for Telegram session secret operations.
These exceptions must NEVER include plaintext secrets, ciphertext, or keys.
"""

class TelegramSessionSecretError(Exception):
    """Base class for all Telegram session secret errors."""
    pass


class TelegramSessionEncryptionError(TelegramSessionSecretError):
    """Raised when encryption of a session secret fails."""
    pass


class TelegramSessionDecryptionError(TelegramSessionSecretError):
    """Raised when decryption of a session secret fails (e.g. wrong key, tampered ciphertext)."""
    pass


class TelegramSessionIntegrityError(TelegramSessionSecretError):
    """Raised when the session bundle is corrupted or missing required fields."""
    pass


class TelegramSessionConfigurationError(TelegramSessionSecretError):
    """Raised when the session secret configuration is invalid (e.g. SecretStore missing)."""
    pass


class TelegramSessionUnavailableError(TelegramSessionSecretError):
    """Raised when attempting to load a session that does not exist."""
    pass


class TelegramSessionCorruptedError(TelegramSessionSecretError):
    """Raised when the persisted session data is irreparably corrupted."""
    pass


class TelegramSessionMigrationError(TelegramSessionSecretError):
    """Raised when migrating a legacy session fails."""
    pass


class TelegramSessionRestoreError(TelegramSessionSecretError):
    """Raised when restoring a session to the TelegramClient fails."""
    pass


class TelegramSessionDeletionError(TelegramSessionSecretError):
    """Raised when deleting a session bundle or files fails."""
    pass
