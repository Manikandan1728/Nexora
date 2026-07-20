"""
app/integrations/telegram/repositories/processing_state_repo.py
[ADDITIVE] TelegramProcessingState repository.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Protocol
from sqlalchemy.orm import Session
from app.integrations.telegram.db.orm_models import TelegramProcessingStateORM


class TelegramProcessingStateRepository(Protocol):
    def get_by_idempotency_key(self, session: Session, key: str) -> TelegramProcessingStateORM | None: ...
    def create(self, session: Session, record: TelegramProcessingStateORM) -> TelegramProcessingStateORM: ...
    def mark_completed(self, session: Session, record: TelegramProcessingStateORM) -> None: ...
    def mark_failed(self, session: Session, record: TelegramProcessingStateORM, error: str) -> None: ...
    def list_stuck(self, session: Session, older_than: datetime) -> list[TelegramProcessingStateORM]: ...


class SqliteTelegramProcessingStateRepository:

    def get_by_idempotency_key(
        self, session: Session, key: str
    ) -> TelegramProcessingStateORM | None:
        return session.query(TelegramProcessingStateORM).filter_by(idempotency_key=key).first()

    def create(
        self, session: Session, record: TelegramProcessingStateORM
    ) -> TelegramProcessingStateORM:
        existing = self.get_by_idempotency_key(session, record.idempotency_key)
        if existing:
            return existing
        session.add(record)
        session.flush()
        return record

    def mark_completed(self, session: Session, record: TelegramProcessingStateORM) -> None:
        record.status = "completed"
        record.completed_at = datetime.now(tz=timezone.utc)
        session.flush()

    def mark_failed(
        self, session: Session, record: TelegramProcessingStateORM, error: str
    ) -> None:
        record.status = "failed"
        record.attempt_count += 1
        record.last_error_code = error[:128]
        session.flush()

    def list_stuck(
        self, session: Session, older_than: datetime
    ) -> list[TelegramProcessingStateORM]:
        """Return processing-state records stuck in 'processing' before cutoff."""
        return (
            session.query(TelegramProcessingStateORM)
            .filter(
                TelegramProcessingStateORM.status == "processing",
                TelegramProcessingStateORM.started_at < older_than,
            )
            .all()
        )
