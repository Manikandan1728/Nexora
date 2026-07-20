# app/integrations/telegram/repositories/__init__.py
# [ADDITIVE]
from .account_repo import TelegramAccountRepository, SqliteTelegramAccountRepository
from .chat_repo import TelegramChatRepository, SqliteTelegramChatRepository
from .message_repo import TelegramMessageRepository, SqliteTelegramMessageRepository
from .chunk_repo import TelegramMessageChunkRepository, SqliteTelegramMessageChunkRepository
from .processing_state_repo import TelegramProcessingStateRepository, SqliteTelegramProcessingStateRepository
from .tombstone_repo import TelegramTombstoneRepository, SqliteTelegramTombstoneRepository

__all__ = [
    "TelegramAccountRepository", "SqliteTelegramAccountRepository",
    "TelegramChatRepository", "SqliteTelegramChatRepository",
    "TelegramMessageRepository", "SqliteTelegramMessageRepository",
    "TelegramMessageChunkRepository", "SqliteTelegramMessageChunkRepository",
    "TelegramProcessingStateRepository", "SqliteTelegramProcessingStateRepository",
    "TelegramTombstoneRepository", "SqliteTelegramTombstoneRepository",
]
