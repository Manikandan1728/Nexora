# app/integrations/telegram/db/__init__.py
# [ADDITIVE] SQLAlchemy ORM layer for Telegram persistence.
from .engine import get_engine, get_session_factory, create_all_tables, DatabaseSettings
from .orm_models import (
    TelegramAccountORM, TelegramChatORM, TelegramMessageORM,
    TelegramAttachmentORM, TelegramMessageChunkORM,
    TelegramProcessingStateORM, TelegramDeletionTombstoneORM,
    Base,
)

__all__ = [
    "get_engine", "get_session_factory", "create_all_tables", "DatabaseSettings",
    "TelegramAccountORM", "TelegramChatORM", "TelegramMessageORM",
    "TelegramAttachmentORM", "TelegramMessageChunkORM",
    "TelegramProcessingStateORM", "TelegramDeletionTombstoneORM",
    "Base",
]
