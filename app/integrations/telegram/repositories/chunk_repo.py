"""
app/integrations/telegram/repositories/chunk_repo.py
[ADDITIVE] TelegramMessageChunk repository — message-to-vector mapping.
"""
from __future__ import annotations
from typing import Protocol
from sqlalchemy.orm import Session
from app.integrations.telegram.db.orm_models import TelegramMessageChunkORM


class TelegramMessageChunkRepository(Protocol):
    def list_active_chunks(self, session: Session, telegram_message_record_id: str) -> list[TelegramMessageChunkORM]: ...
    def add_chunks(self, session: Session, chunks: list[TelegramMessageChunkORM]) -> None: ...
    def deactivate_chunks(self, session: Session, telegram_message_record_id: str) -> list[str]: ...
    def delete_by_vector_ids(self, session: Session, vector_ids: list[str]) -> int: ...


class SqliteTelegramMessageChunkRepository:
    """SQLite-backed TelegramMessageChunk repository."""

    def list_active_chunks(
        self, session: Session, telegram_message_record_id: str
    ) -> list[TelegramMessageChunkORM]:
        return (
            session.query(TelegramMessageChunkORM)
            .filter_by(telegram_message_record_id=telegram_message_record_id, is_active=True)
            .all()
        )

    def list_all_chunks(
        self, session: Session, telegram_message_record_id: str
    ) -> list[TelegramMessageChunkORM]:
        return (
            session.query(TelegramMessageChunkORM)
            .filter_by(telegram_message_record_id=telegram_message_record_id)
            .all()
        )

    def add_chunks(self, session: Session, chunks: list[TelegramMessageChunkORM]) -> None:
        for chunk in chunks:
            session.add(chunk)
        session.flush()

    def deactivate_chunks(
        self, session: Session, telegram_message_record_id: str
    ) -> list[str]:
        """Deactivate all active chunks for a message. Returns the vector_ids that were deactivated."""
        active = self.list_active_chunks(session, telegram_message_record_id)
        vector_ids = []
        for chunk in active:
            chunk.is_active = False
            vector_ids.append(chunk.vector_id)
        session.flush()
        return vector_ids

    def delete_by_vector_ids(self, session: Session, vector_ids: list[str]) -> int:
        """Hard-delete chunk records by vector_id. Returns count deleted."""
        if not vector_ids:
            return 0
        deleted = (
            session.query(TelegramMessageChunkORM)
            .filter(TelegramMessageChunkORM.vector_id.in_(vector_ids))
            .delete(synchronize_session="fetch")
        )
        session.flush()
        return deleted

    def get_by_vector_id(
        self, session: Session, vector_id: str
    ) -> TelegramMessageChunkORM | None:
        return session.query(TelegramMessageChunkORM).filter_by(vector_id=vector_id).first()
