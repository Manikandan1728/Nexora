"""
app/integrations/telegram/security/session_contexts.py

[ADDITIVE] Part 2C — Mission 1 (Centralized Encryption Contexts)

Centralized context string definitions for Telegram session secret encryption.
Using exact context strings ensures that ciphertext generated for one type of
secret (e.g. phone number) cannot be accidentally or maliciously decrypted as
another type of secret (e.g. database key).
"""

# The opaque session reference string that locates/identifies the TDLib session.
TELEGRAM_SESSION_REFERENCE_CONTEXT = "telegram_session_reference"

# The encryption key for the TDLib sqlite database.
TELEGRAM_TDLIB_DATABASE_KEY_CONTEXT = "telegram_tdlib_database_key"

# The encryption key for the TDLib files sqlite database (if separate).
TELEGRAM_TDLIB_FILES_DATABASE_KEY_CONTEXT = "telegram_tdlib_files_database_key"

# A sensitive local session path/locator that should not be stored in plaintext.
TELEGRAM_SESSION_LOCATOR_CONTEXT = "telegram_session_locator"

# The MTProto Telethon string session.
TELEGRAM_MTPROTO_SESSION_CONTEXT = "telegram_mtproto_session"
