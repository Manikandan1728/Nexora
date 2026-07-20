"""
app/integrations/telegram/security/phone_secret_service.py

[ADDITIVE] Part 2B — Phases 3, 10, 12, 13.

Dedicated application service that wraps ``SecretStore`` for Telegram
phone-number encryption, decryption, masking, and legacy-value
classification.

Design decisions
----------------
- This is the **only** code path that encrypts or decrypts phone numbers.
- Decryption is restricted to this service; no API route, ORM model,
  response serializer, or frontend code may call decrypt directly.
- ``encrypt_phone_number`` rejects values that already carry the
  ``nexora:v1:`` prefix (double-encryption prevention — Phase 12).
- Legacy-value classification (Phase 10) enables the migration service
  to handle empty, already-encrypted, plaintext, invalid, and corrupted
  stored values without data loss.

Security invariants
-------------------
- Plaintext phone numbers are never logged.
- Ciphertext is never logged.
- Exceptions never contain phone data (enforced by typed errors from
  Phase 4).
"""
from __future__ import annotations

import logging
from enum import Enum

from app.security.secrets.base import SecretStore
from app.security.secrets.exceptions import (
    SecretDecryptionError,
    SecretEncryptionError,
    SecretStoreError,
)
from app.integrations.telegram.security.phone_number import TelegramPhoneNumber
from app.integrations.telegram.security.errors import (
    TelegramPhoneEncryptionError,
    TelegramPhoneDecryptionError,
    TelegramPhoneNumberValidationError,
)

logger = logging.getLogger(__name__)

_CIPHERTEXT_PREFIX = "nexora:v1:"


class StoredValueCategory(str, Enum):
    """Classification of a value read from the ``phone_number_encrypted``
    database column — used by the migration service (Phase 11)."""

    EMPTY = "empty"
    ALREADY_ENCRYPTED = "already_encrypted"
    LEGACY_PLAINTEXT = "legacy_plaintext"
    INVALID_LEGACY = "invalid_legacy"
    CORRUPTED_ENCRYPTED = "corrupted_encrypted"


class TelegramPhoneSecretService:
    """Encrypt, decrypt, mask, and classify Telegram phone numbers.

    This service is the **sole authorized entry point** for phone-number
    encryption and decryption.  It delegates to the injected
    ``SecretStore`` and never calls AES-GCM directly.

    Authorized decryption call sites (Phase 13):
      1. ``decrypt_phone_number()``
      2. ``get_masked_phone_number()`` (calls decrypt internally)
      3. ``TelegramPhoneNumberMigrationService`` (validation only)

    Forbidden decryption call sites:
      - API routes / response serializers
      - ORM models
      - Frontend
      - Logging middleware / analytics
      - Query / RAG pipeline
    """

    CONTEXT: str = "telegram_phone_number"
    """AAD context string bound to every phone-number ciphertext."""

    CIPHERTEXT_PREFIX: str = _CIPHERTEXT_PREFIX
    """Wire-format prefix that identifies a Nexora encrypted payload."""

    def __init__(self, secret_store: SecretStore) -> None:
        self._store = secret_store

    # ------------------------------------------------------------------
    # Encryption
    # ------------------------------------------------------------------

    def encrypt_phone_number(self, raw_phone: str) -> str:
        """Validate, normalize, and encrypt a raw phone-number string.

        Parameters
        ----------
        raw_phone:
            User-provided phone number (may contain spaces, hyphens, etc.).

        Returns
        -------
        str
            Ciphertext token in ``nexora:v1:…`` format.

        Raises
        ------
        TelegramPhoneNumberValidationError
            If the input fails validation.
        TelegramPhoneEncryptionError
            If encryption fails, or if the input is already encrypted
            (double-encryption prevention — Phase 12).
        """
        # Phase 12: reject already-encrypted values.
        if self.is_encrypted_payload(raw_phone):
            raise TelegramPhoneEncryptionError(
                "Input is already encrypted — refusing to double-encrypt.",
                safe_detail="double_encryption_rejected",
            )

        # Phase 1: validate and normalize.
        phone = TelegramPhoneNumber.parse(raw_phone)

        # Phase 3: encrypt via SecretStore with AAD context.
        try:
            ciphertext = self._store.encrypt(
                phone.normalized, context=self.CONTEXT
            )
        except SecretEncryptionError as exc:
            raise TelegramPhoneEncryptionError(
                "Phone number encryption failed.",
                safe_detail=f"secret_store:{exc.safe_detail}",
            ) from exc
        except SecretStoreError as exc:
            raise TelegramPhoneEncryptionError(
                "Phone number encryption failed (store error).",
                safe_detail=f"secret_store:{type(exc).__name__}",
            ) from exc

        logger.debug("Phone number encrypted successfully (value not logged).")
        return ciphertext

    # ------------------------------------------------------------------
    # Decryption (restricted — Phase 13)
    # ------------------------------------------------------------------

    def decrypt_phone_number(self, ciphertext: str) -> str:
        """Decrypt a stored phone-number ciphertext and re-validate.

        Parameters
        ----------
        ciphertext:
            ``nexora:v1:…`` token from the database.

        Returns
        -------
        str
            Normalized E.164-style phone number (temporary plaintext —
            caller must not persist, log, or return it).

        Raises
        ------
        TelegramPhoneDecryptionError
            If decryption fails (wrong key, wrong context, corrupted
            payload, etc.).
        TelegramPhoneNumberValidationError
            If the decrypted plaintext is not a valid phone number
            (indicates data corruption).
        """
        try:
            plaintext = self._store.decrypt(ciphertext, context=self.CONTEXT)
        except SecretDecryptionError as exc:
            raise TelegramPhoneDecryptionError(
                "Phone number decryption failed.",
                safe_detail=f"secret_store:{exc.safe_detail}",
            ) from exc
        except SecretStoreError as exc:
            raise TelegramPhoneDecryptionError(
                "Phone number decryption failed (store error).",
                safe_detail=f"secret_store:{type(exc).__name__}",
            ) from exc

        # Re-validate the decrypted result to catch data corruption.
        phone = TelegramPhoneNumber.parse(plaintext)

        logger.debug("Phone number decrypted successfully (value not logged).")
        return phone.normalized

    # ------------------------------------------------------------------
    # Masking
    # ------------------------------------------------------------------

    def get_masked_phone_number(self, ciphertext: str) -> str:
        """Decrypt and mask a stored phone-number ciphertext.

        Returns
        -------
        str
            Masked display value (e.g. ``+91 ******3210``).

        Raises
        ------
        TelegramPhoneDecryptionError
            If decryption fails.
        """
        normalized = self.decrypt_phone_number(ciphertext)
        phone = TelegramPhoneNumber(normalized=normalized)
        return phone.masked()

    # ------------------------------------------------------------------
    # Classification (Phases 10 & 12)
    # ------------------------------------------------------------------

    def is_encrypted_payload(self, value: str) -> bool:
        """Return ``True`` if *value* looks like a Nexora encrypted token."""
        return bool(value) and value.startswith(_CIPHERTEXT_PREFIX)

    def classify_stored_value(self, value: str | None) -> StoredValueCategory:
        """Classify a value read from the ``phone_number_encrypted`` column.

        Used by the migration service to decide what action to take for
        each stored record.

        Categories
        ----------
        EMPTY
            ``None`` or whitespace-only.
        ALREADY_ENCRYPTED
            Starts with ``nexora:v1:`` and is decryptable.
        CORRUPTED_ENCRYPTED
            Starts with ``nexora:v1:`` but decryption fails.
        LEGACY_PLAINTEXT
            Parseable as a valid phone number by ``TelegramPhoneNumber``.
        INVALID_LEGACY
            Not empty, not encrypted, and not a valid phone number.
        """
        if not value or not value.strip():
            return StoredValueCategory.EMPTY

        if self.is_encrypted_payload(value):
            # Attempt to decrypt to verify integrity.
            try:
                self.decrypt_phone_number(value)
                return StoredValueCategory.ALREADY_ENCRYPTED
            except (TelegramPhoneDecryptionError, TelegramPhoneNumberValidationError):
                return StoredValueCategory.CORRUPTED_ENCRYPTED

        # Not encrypted — try to parse as a phone number.
        try:
            TelegramPhoneNumber.parse(value)
            return StoredValueCategory.LEGACY_PLAINTEXT
        except TelegramPhoneNumberValidationError:
            return StoredValueCategory.INVALID_LEGACY
