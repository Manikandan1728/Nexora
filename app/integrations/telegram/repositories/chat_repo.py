"""
app/integrations/telegram/repositories/chat_repo.py
[ADDITIVE] TelegramChat repository.
"""
from __future__ import annotations
from typing import Protocol
from sqlalchemy.orm import Session
from app.integrations.telegram.db.orm_models import TelegramChatORM


class TelegramChatRepository(Protocol):
    def get_owned_chat(
        self, session: Session, owner_id: str, source_account_id: str, conversation_id: str
    ) -> TelegramChatORM | None: ...

    def get_owned_chats(
        self, session: Session, owner_id: str,
        source_account_id: str | None, conversation_ids: list[str]
    ) -> list[TelegramChatORM]: ...

    def upsert(self, session: Session, record: TelegramChatORM) -> TelegramChatORM: ...
    def mark_deleted(self, session: Session, record: TelegramChatORM) -> None: ...


class SqliteTelegramChatRepository:
    """SQLite-backed TelegramChat repository."""

    def get_owned_chat(
        self, session: Session, owner_id: str,
        source_account_id: str, conversation_id: str
    ) -> TelegramChatORM | None:
        """Returns active (not soft-deleted) chat owned by this owner."""
        from app.integrations.telegram.db.orm_models import TelegramAccountORM
        return (
            session.query(TelegramChatORM)
            .join(TelegramAccountORM, TelegramChatORM.telegram_account_id == TelegramAccountORM.id)
            .filter(
                TelegramChatORM.owner_id == owner_id,
                TelegramChatORM.telegram_chat_id == conversation_id,
                TelegramChatORM.is_deleted == False,
                TelegramAccountORM.telegram_user_id == source_account_id,
            )
            .first()
        )

    def get_owned_chats(
        self, session: Session, owner_id: str,
        source_account_id: str | None,
        conversation_ids: list[str],
    ) -> list[TelegramChatORM]:
        """Returns all non-deleted owned chats matching the requested IDs."""
        from app.integrations.telegram.db.orm_models import TelegramAccountORM
        q = (
            session.query(TelegramChatORM)
            .join(TelegramAccountORM, TelegramChatORM.telegram_account_id == TelegramAccountORM.id)
            .filter(
                TelegramChatORM.owner_id == owner_id,
                TelegramChatORM.telegram_chat_id.in_(conversation_ids),
                TelegramChatORM.is_deleted == False,
            )
        )
        if source_account_id:
            q = q.filter(TelegramAccountORM.telegram_user_id == source_account_id)
        return q.all()

    def upsert(self, session: Session, record: TelegramChatORM) -> TelegramChatORM:
        existing = (
            session.query(TelegramChatORM)
            .filter_by(
                telegram_account_id=record.telegram_account_id,
                telegram_chat_id=record.telegram_chat_id,
            )
            .first()
        )
        if existing:
            for attr in ("chat_title", "chat_type", "indexing_enabled",
                         "indexing_enabled_at", "last_processed_message_id"):
                val = getattr(record, attr, None)
                if val is not None:
                    setattr(existing, attr, val)
            session.flush()
            return existing
        session.add(record)
        session.flush()
        return record

    def mark_deleted(self, session: Session, record: TelegramChatORM) -> None:
        record.is_deleted = True
        session.flush()
