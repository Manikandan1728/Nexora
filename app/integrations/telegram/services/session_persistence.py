"""
app/integrations/telegram/services/session_persistence.py

[ADDITIVE] Part 2C — Phases 7, 8, 9
Persistence service for saving and loading Telegram session bundles.
Ensures failure-safe atomic writes to the database.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations.telegram.db.orm_models import TelegramAccountORM
from app.integrations.telegram.models.session_models import (
    DecryptedTelegramSessionBundle,
    EncryptedTelegramSessionBundle,
    TelegramSessionStatus,
    TelegramSessionValidationResult,
)
from app.integrations.telegram.repositories.account_repo import TelegramAccountRepository
from app.integrations.telegram.security.session_errors import (
    TelegramSessionCorruptedError,
    TelegramSessionEncryptionError,
    TelegramSessionDecryptionError,
)
from app.integrations.telegram.security.session_secret_service import TelegramSessionSecretService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TelegramSessionPersistenceService:
    """
    Manages atomic persistence and loading of encrypted session bundles.
    Delegates cryptography to TelegramSessionSecretService.
    """

    def __init__(
        self,
        secret_service: TelegramSessionSecretService,
        account_repo: TelegramAccountRepository,
    ) -> None:
        self._secret_service = secret_service
        self._account_repo = account_repo

    def store_session_bundle(
        self,
        db_session: Session,
        owner_id: str,
        telegram_user_id: str,
        decrypted_bundle: DecryptedTelegramSessionBundle,
    ) -> TelegramAccountORM:
        """
        Phase 8: Failure-safe store flow.
        Encrypts the bundle and saves it. If encryption fails, no partial state
        is persisted.
        """
        # Encrypt fields
        enc_ref = None
        if decrypted_bundle.session_reference:
            enc_ref = self._secret_service.encrypt_session_reference(
                decrypted_bundle.session_reference.get_secret_value()
            )

        enc_db = None
        if decrypted_bundle.tdlib_database_key:
            enc_db = self._secret_service.encrypt_tdlib_database_key(
                decrypted_bundle.tdlib_database_key.get_secret_value()
            )

        enc_fdb = None
        if decrypted_bundle.tdlib_files_database_key:
            enc_fdb = self._secret_service.encrypt_tdlib_files_database_key(
                decrypted_bundle.tdlib_files_database_key.get_secret_value()
            )

        enc_loc = None
        if decrypted_bundle.session_locator:
            enc_loc = self._secret_service.encrypt_session_locator(
                decrypted_bundle.session_locator.get_secret_value()
            )

        enc_bundle = EncryptedTelegramSessionBundle(
            session_reference_encrypted=enc_ref,
            tdlib_database_key_encrypted=enc_db,
            tdlib_files_database_key_encrypted=enc_fdb,
            session_locator_encrypted=enc_loc,
        )

        val_result = self._secret_service.validate_session_bundle(enc_bundle)

        account = self._account_repo.get_owned_account(db_session, owner_id, telegram_user_id)
        if not account:
            # We are creating a new account record
            account = TelegramAccountORM(
                id="temporary_will_be_overridden_in_repo",
                owner_id=owner_id,
                telegram_user_id=telegram_user_id,
            )

        now = _utcnow()
        if account.session_status == TelegramSessionStatus.ABSENT.value and val_result.status != TelegramSessionStatus.ABSENT:
            account.session_created_at = now
        
        account.session_status = val_result.status.value
        account.session_reference_encrypted = enc_bundle.session_reference_encrypted
        account.tdlib_database_key_encrypted = enc_bundle.tdlib_database_key_encrypted
        account.tdlib_files_database_key_encrypted = enc_bundle.tdlib_files_database_key_encrypted
        account.session_locator_encrypted = enc_bundle.session_locator_encrypted
        account.session_updated_at = now

        return self._account_repo.upsert(db_session, account)

    def load_session_bundle(
        self,
        db_session: Session,
        owner_id: str,
        telegram_user_id: str,
    ) -> DecryptedTelegramSessionBundle | None:
        """
        Phase 9: Failure-safe restore flow.
        Loads and decrypts the session. If decryption fails, returns None and
        marks the session status as unreadable.
        """
        from pydantic import SecretStr

        account = self._account_repo.get_owned_account(db_session, owner_id, telegram_user_id)
        if not account:
            return None

        # Verify it actually has data
        enc_bundle = EncryptedTelegramSessionBundle(
            session_reference_encrypted=account.session_reference_encrypted,
            tdlib_database_key_encrypted=account.tdlib_database_key_encrypted,
            tdlib_files_database_key_encrypted=account.tdlib_files_database_key_encrypted,
            session_locator_encrypted=account.session_locator_encrypted,
        )

        val = self._secret_service.validate_session_bundle(enc_bundle)
        if val.status == TelegramSessionStatus.ABSENT:
            return None

        try:
            dec_ref = None
            if enc_bundle.session_reference_encrypted:
                dec_ref = SecretStr(self._secret_service.decrypt_session_reference(
                    enc_bundle.session_reference_encrypted
                ))

            dec_db = None
            if enc_bundle.tdlib_database_key_encrypted:
                dec_db = SecretStr(self._secret_service.decrypt_tdlib_database_key(
                    enc_bundle.tdlib_database_key_encrypted
                ))
            
            dec_fdb = None
            if enc_bundle.tdlib_files_database_key_encrypted:
                dec_fdb = SecretStr(self._secret_service.decrypt_tdlib_files_database_key(
                    enc_bundle.tdlib_files_database_key_encrypted
                ))

            dec_loc = None
            if enc_bundle.session_locator_encrypted:
                dec_loc = SecretStr(self._secret_service.decrypt_session_locator(
                    enc_bundle.session_locator_encrypted
                ))

            # Update last restored timestamp
            account.session_last_restored_at = _utcnow()
            self._account_repo.upsert(db_session, account)

            return DecryptedTelegramSessionBundle(
                session_reference=dec_ref,
                tdlib_database_key=dec_db,
                tdlib_files_database_key=dec_fdb,
                session_locator=dec_loc,
            )

        except (TelegramSessionDecryptionError, Exception) as e:
            logger.error(
                f"Failed to decrypt session bundle for owner_id={owner_id}, "
                f"telegram_user_id={telegram_user_id}. Marking as unreadable. Error: {e}"
            )
            # Apply Corrupted Ciphertext Policy (Phase 17)
            account.session_status = TelegramSessionStatus.UNREADABLE.value
            self._account_repo.upsert(db_session, account)
            raise TelegramSessionCorruptedError("Session bundle decryption failed.") from e

    def clear_session_bundle(
        self,
        db_session: Session,
        owner_id: str,
        telegram_user_id: str,
    ) -> None:
        """
        Clears the session bundle securely.
        Used during logout or when deleting an account.
        """
        account = self._account_repo.get_owned_account(db_session, owner_id, telegram_user_id)
        if not account:
            return

        account.session_status = TelegramSessionStatus.ABSENT.value
        account.session_reference_encrypted = None
        account.tdlib_database_key_encrypted = None
        account.tdlib_files_database_key_encrypted = None
        account.session_locator_encrypted = None
        
        # We don't wipe session_created_at/session_last_restored_at intentionally
        # as they provide audit trail, but we update session_updated_at.
        account.session_updated_at = _utcnow()
        self._account_repo.upsert(db_session, account)
