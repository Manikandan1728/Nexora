"""
app/integrations/telegram/security/errors.py — Typed phone-number exceptions.

[ADDITIVE] Part 2B — Phase 4.

Security invariant: NO exception message, repr, or safe_detail field may
ever contain a plaintext phone number, a normalized phone number,
ciphertext, or encryption key material.  Messages use only safe reason
codes, operation names, and opaque identifiers.
"""
from __future__ import annotations


class TelegramPhoneNumberError(Exception):
    """Base class for all Telegram phone-number errors.

    Follows the same pattern as ``SecretStoreError``: a human-readable
    ``message`` plus an optional ``safe_detail`` that may be logged.
    Neither field may contain sensitive phone data.
    """

    def __init__(self, message: str, *, safe_detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        # safe_detail may be logged; must never contain phone numbers or ciphertext
        self.safe_detail = safe_detail or ""


class TelegramPhoneNumberValidationError(TelegramPhoneNumberError):
    """Phone-number input failed validation (format, length, characters).

    The ``reason`` code describes the failure category without echoing the
    raw input.
    """

    def __init__(
        self,
        reason: str,
        *,
        safe_detail: str | None = None,
    ) -> None:
        super().__init__(
            f"Phone number validation failed: {reason}",
            safe_detail=safe_detail,
        )
        self.reason = reason


class TelegramPhoneEncryptionError(TelegramPhoneNumberError):
    """Encryption of a phone number failed.

    Wraps underlying ``SecretEncryptionError`` without leaking plaintext.
    """


class TelegramPhoneDecryptionError(TelegramPhoneNumberError):
    """Decryption of a stored phone-number ciphertext failed.

    Covers wrong key, wrong context, integrity failure, and corrupted
    payloads.  Never includes the ciphertext in the message.
    """


class TelegramPhoneMigrationError(TelegramPhoneNumberError):
    """A legacy phone-number value could not be migrated.

    Includes a safe ``status`` code (e.g. ``"invalid"``, ``"corrupted"``)
    and optionally the account ID, but never the phone value itself.
    """

    def __init__(
        self,
        status: str,
        *,
        account_id: str | None = None,
        safe_detail: str | None = None,
    ) -> None:
        ctx = f" (account={account_id})" if account_id else ""
        super().__init__(
            f"Phone number migration failed: {status}{ctx}",
            safe_detail=safe_detail,
        )
        self.status = status
        self.account_id = account_id
