"""
app/integrations/telegram/repositories/checkpoint_repo.py
[ADDITIVE] TelegramCheckpoint repository for live sync.
"""
from __future__ import annotations
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from app.integrations.telegram.db.orm_models import TelegramCheckpointORM


class TelegramCheckpointRepository(Protocol):
    def get_checkpoint(self, session: Session, account_id: str) -> TelegramCheckpointORM | None: ...
    def update_checkpoint(
        self, session: Session, account_id: str, timestamp: datetime | None, message_id: str | None
    ) -> TelegramCheckpointORM: ...


class SqliteTelegramCheckpointRepository:
    """SQLite-backed TelegramCheckpoint repository."""

    def get_checkpoint(self, session: Session, account_id: str) -> TelegramCheckpointORM | None:
        return session.query(TelegramCheckpointORM).filter_by(account_id=account_id).first()

    def update_checkpoint(
        self, session: Session, account_id: str, timestamp: datetime | None, message_id: str | None
    ) -> TelegramCheckpointORM:
        record = self.get_checkpoint(session, account_id)
        if not record:
            record = TelegramCheckpointORM(
                account_id=account_id,
                last_processed_timestamp=timestamp,
                last_processed_message_id=message_id,
            )
            session.add(record)
        else:
            if timestamp is not None:
                record.last_processed_timestamp = timestamp
            if message_id is not None:
                record.last_processed_message_id = message_id
            
        session.flush()
        return record
