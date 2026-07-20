"""
app/integrations/telegram/repositories/message_repo.py
[ADDITIVE] TelegramMessage repository.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Protocol
from sqlalchemy.orm import Session
from app.integrations.telegram.db.orm_models import TelegramMessageORM


class TelegramMessageRepository(Protocol):
    def get_by_source_identity(
        self, session: Session,
        source_account_id: str, conversation_id: str, source_message_id: str
    ) -> TelegramMessageORM | None: ...
    def upsert_new_message(self, session: Session, record: TelegramMessageORM) -> TelegramMessageORM: ...
    def mark_edited(self, session: Session, record: TelegramMessageORM, new_text: str | None) -> None: ...
    def mark_deleted(self, session: Session, record: TelegramMessageORM) -> None: ...


class SqliteTelegramMessageRepository:
    """SQLite-backed TelegramMessage repository."""

    def get_by_source_identity(
        self, session: Session,
        source_account_id: str, conversation_id: str, source_message_id: str
    ) -> TelegramMessageORM | None:
        return (
            session.query(TelegramMessageORM)
            .filter_by(
                telegram_account_id=source_account_id,
                telegram_chat_id=conversation_id,
                telegram_message_id=source_message_id,
            )
            .first()
        )

    def upsert_new_message(
        self, session: Session, record: TelegramMessageORM
    ) -> TelegramMessageORM:
        existing = self.get_by_source_identity(
            session,
            record.telegram_account_id,
            record.telegram_chat_id,
            record.telegram_message_id,
        )
        if existing:
            return existing  # Already exists; caller handles idempotency
        session.add(record)
        session.flush()
        return record

    def mark_edited(
        self, session: Session, record: TelegramMessageORM, new_text: str | None
    ) -> None:
        record.is_edited = True
        record.current_version += 1
        if new_text is not None:
            record.raw_text = new_text
        record.updated_at = datetime.now(tz=timezone.utc)
        session.flush()

    def mark_deleted(self, session: Session, record: TelegramMessageORM) -> None:
        record.is_deleted = True
        record.processing_status = "deleted"
        record.updated_at = datetime.now(tz=timezone.utc)
        session.flush()
