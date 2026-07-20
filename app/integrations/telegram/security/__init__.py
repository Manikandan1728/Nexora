"""
app/integrations/telegram/security/__init__.py

[ADDITIVE] Part 2B — Missions 1 & 2.

Public surface for Telegram phone-number security primitives:
  - TelegramPhoneNumber value object (Phase 1 + 2)
  - Typed phone-number exceptions (Phase 4)
  - TelegramPhoneSecretService (Phase 3)
  - StoredValueCategory (Phase 10)
  - Migration service types (Phase 11)
"""
from __future__ import annotations

from app.integrations.telegram.security.phone_number import TelegramPhoneNumber
from app.integrations.telegram.security.errors import (
    TelegramPhoneNumberError,
    TelegramPhoneNumberValidationError,
    TelegramPhoneEncryptionError,
    TelegramPhoneDecryptionError,
    TelegramPhoneMigrationError,
)
from app.integrations.telegram.security.phone_secret_service import (
    TelegramPhoneSecretService,
    StoredValueCategory,
)
from app.integrations.telegram.security.migration_service import (
    TelegramPhoneNumberMigrationService,
    PhoneMigrationStatus,
    PhoneMigrationResult,
    PhoneMigrationSummary,
)

__all__ = [
    # Phase 1+2: value object
    "TelegramPhoneNumber",
    # Phase 3: secret service
    "TelegramPhoneSecretService",
    "StoredValueCategory",
    # Phase 4: errors
    "TelegramPhoneNumberError",
    "TelegramPhoneNumberValidationError",
    "TelegramPhoneEncryptionError",
    "TelegramPhoneDecryptionError",
    "TelegramPhoneMigrationError",
    # Phase 11: migration
    "TelegramPhoneNumberMigrationService",
    "PhoneMigrationStatus",
    "PhoneMigrationResult",
    "PhoneMigrationSummary",
]
