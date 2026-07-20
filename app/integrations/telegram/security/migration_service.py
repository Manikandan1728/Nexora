"""
app/integrations/telegram/security/migration_service.py

[ADDITIVE] Part 2B — Phase 11.

One-time migration service for converting legacy plaintext phone numbers
to encrypted values.  Idempotent, batch-safe, transactional per record.

Security invariants
-------------------
- Phone values (plaintext **and** ciphertext) are never logged.
- Results contain only account IDs, status codes, and counts.
- Corrupted ciphertext is never overwritten automatically.
- Invalid legacy values are flagged, not silently deleted.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

from app.integrations.telegram.db.orm_models import TelegramAccountORM
from app.integrations.telegram.security.errors import (
    TelegramPhoneEncryptionError,
    TelegramPhoneMigrationError,
)
from app.integrations.telegram.security.phone_secret_service import (
    StoredValueCategory,
    TelegramPhoneSecretService,
)

logger = logging.getLogger(__name__)


class PhoneMigrationStatus(str, Enum):
    """Outcome of a single account's phone-number migration attempt."""

    ALREADY_ENCRYPTED = "already_encrypted"
    ENCRYPTED = "encrypted"
    EMPTY = "empty"
    INVALID = "invalid"
    CORRUPTED = "corrupted"
    FAILED = "failed"


@dataclass
class PhoneMigrationResult:
    """Result of migrating one account's phone number."""

    account_id: str
    status: PhoneMigrationStatus


@dataclass
class PhoneMigrationSummary:
    """Aggregate result of a migration run."""

    total: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    results: list[PhoneMigrationResult] = field(default_factory=list)


# Mapping from classification to migration status.
_CATEGORY_TO_STATUS = {
    StoredValueCategory.EMPTY: PhoneMigrationStatus.EMPTY,
    StoredValueCategory.ALREADY_ENCRYPTED: PhoneMigrationStatus.ALREADY_ENCRYPTED,
    StoredValueCategory.CORRUPTED_ENCRYPTED: PhoneMigrationStatus.CORRUPTED,
    StoredValueCategory.INVALID_LEGACY: PhoneMigrationStatus.INVALID,
}


class TelegramPhoneNumberMigrationService:
    """Migrate legacy plaintext phone numbers to encrypted storage.

    Usage::

        svc = TelegramPhoneNumberMigrationService(phone_secret_service, session)
        summary = svc.migrate_all(dry_run=True)   # preview
        summary = svc.migrate_all(dry_run=False)   # commit
    """

    def __init__(
        self,
        phone_secret_service: TelegramPhoneSecretService,
        session: Session,
    ) -> None:
        self._phone_svc = phone_secret_service
        self._session = session

    # ------------------------------------------------------------------
    # Single-record migration
    # ------------------------------------------------------------------

    def migrate_account(
        self,
        account: TelegramAccountORM,
        *,
        dry_run: bool = False,
    ) -> PhoneMigrationResult:
        """Classify and, if needed, encrypt a single account's phone number.

        Parameters
        ----------
        account:
            ORM record with ``phone_number_encrypted`` field.
        dry_run:
            If ``True``, classify only — do not write to the database.

        Returns
        -------
        PhoneMigrationResult
            Outcome with status code and account ID.
        """
        value = account.phone_number_encrypted
        category = self._phone_svc.classify_stored_value(value)

        # Non-plaintext categories — return status without modifying.
        if category != StoredValueCategory.LEGACY_PLAINTEXT:
            status = _CATEGORY_TO_STATUS.get(category, PhoneMigrationStatus.FAILED)
            return PhoneMigrationResult(account_id=account.id, status=status)

        # Legacy plaintext — encrypt it.
        if dry_run:
            return PhoneMigrationResult(
                account_id=account.id,
                status=PhoneMigrationStatus.ENCRYPTED,
            )

        try:
            # value is guaranteed non-None here (LEGACY_PLAINTEXT classification).
            ciphertext = self._phone_svc.encrypt_phone_number(value)  # type: ignore[arg-type]
            account.phone_number_encrypted = ciphertext
            self._session.flush()
            logger.info(
                "Migrated phone number for account=%s (value not logged).",
                account.id,
            )
            return PhoneMigrationResult(
                account_id=account.id,
                status=PhoneMigrationStatus.ENCRYPTED,
            )
        except (TelegramPhoneEncryptionError, TelegramPhoneMigrationError) as exc:
            logger.warning(
                "Migration failed for account=%s: %s",
                account.id,
                exc.safe_detail,
            )
            return PhoneMigrationResult(
                account_id=account.id,
                status=PhoneMigrationStatus.FAILED,
            )

    # ------------------------------------------------------------------
    # Batch migration
    # ------------------------------------------------------------------

    def migrate_all(self, *, dry_run: bool = False) -> PhoneMigrationSummary:
        """Migrate all accounts in the database.

        Parameters
        ----------
        dry_run:
            If ``True``, classify and report without writing.

        Returns
        -------
        PhoneMigrationSummary
            Aggregate counts by status.
        """
        accounts = self._session.query(TelegramAccountORM).all()
        summary = PhoneMigrationSummary(total=len(accounts))

        for account in accounts:
            result = self.migrate_account(account, dry_run=dry_run)
            summary.results.append(result)
            status_key = result.status.value
            summary.by_status[status_key] = summary.by_status.get(status_key, 0) + 1

        if not dry_run:
            self._session.commit()
            logger.info(
                "Phone number migration complete: total=%d counts=%s",
                summary.total,
                summary.by_status,
            )
        else:
            logger.info(
                "Phone number migration dry-run: total=%d counts=%s",
                summary.total,
                summary.by_status,
            )

        return summary
