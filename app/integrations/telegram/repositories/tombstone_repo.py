"""
app/integrations/telegram/repositories/tombstone_repo.py
[ADDITIVE] TelegramDeletionTombstone repository.
"""
from __future__ import annotations
from typing import Protocol
from sqlalchemy.orm import Session
from app.integrations.telegram.db.orm_models import TelegramDeletionTombstoneORM


class TelegramTombstoneRepository(Protocol):
    def exists(self, session: Session, source_account_id: str, conversation_id: str, source_message_id: str) -> bool: ...
    def create(self, session: Session, record: TelegramDeletionTombstoneORM) -> TelegramDeletionTombstoneORM: ...


class SqliteTelegramTombstoneRepository:

    def exists(
        self, session: Session,
        source_account_id: str, conversation_id: str, source_message_id: str
    ) -> bool:
        return (
            session.query(TelegramDeletionTombstoneORM)
            .filter_by(
                source_account_id=source_account_id,
                conversation_id=conversation_id,
                source_message_id=source_message_id,
            )
            .first()
        ) is not None

    def create(
        self, session: Session, record: TelegramDeletionTombstoneORM
    ) -> TelegramDeletionTombstoneORM:
        # Idempotent: if tombstone already exists, return it
        existing = (
            session.query(TelegramDeletionTombstoneORM)
            .filter_by(
                source_account_id=record.source_account_id,
                conversation_id=record.conversation_id,
                source_message_id=record.source_message_id,
            )
            .first()
        )
        if existing:
            return existing
        session.add(record)
        session.flush()
        return record
