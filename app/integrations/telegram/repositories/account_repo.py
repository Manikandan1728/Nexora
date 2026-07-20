"""
app/integrations/telegram/repositories/account_repo.py
[ADDITIVE] TelegramAccount repository.
"""
from __future__ import annotations
from typing import Protocol
from sqlalchemy.orm import Session
from app.integrations.telegram.db.orm_models import TelegramAccountORM


class TelegramAccountRepository(Protocol):
    def get_owned_account(self, owner_id: str, source_account_id: str) -> TelegramAccountORM | None: ...
    def get_by_id(self, session: Session, account_id: str) -> TelegramAccountORM | None: ...
    def upsert(self, session: Session, record: TelegramAccountORM) -> TelegramAccountORM: ...


class SqliteTelegramAccountRepository:
    """SQLite-backed TelegramAccount repository."""

    def get_owned_account(
        self, session: Session, owner_id: str, source_account_id: str
    ) -> TelegramAccountORM | None:
        return (
            session.query(TelegramAccountORM)
            .filter_by(owner_id=owner_id, telegram_user_id=source_account_id, is_active=True)
            .first()
        )

    def get_by_id(self, session: Session, account_id: str) -> TelegramAccountORM | None:
        return session.query(TelegramAccountORM).filter_by(id=account_id).first()

    def upsert(self, session: Session, record: TelegramAccountORM) -> TelegramAccountORM:
        existing = (
            session.query(TelegramAccountORM)
            .filter_by(owner_id=record.owner_id, telegram_user_id=record.telegram_user_id)
            .first()
        )
        if existing:
            for attr in (
                "display_name", "username", "phone_number_encrypted",
                "authorization_status", "session_status",
                "session_reference_encrypted",
                "tdlib_database_key_encrypted",
                "tdlib_files_database_key_encrypted",
                "session_locator_encrypted",
                "is_active", "connected_at", "last_active_at",
                "session_created_at", "session_updated_at", "session_last_restored_at",
            ):
                val = getattr(record, attr, None)
                if val is not None:
                    setattr(existing, attr, val)
            session.flush()
            return existing
        session.add(record)
        session.flush()
        return record
