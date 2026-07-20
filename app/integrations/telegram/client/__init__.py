# app/integrations/telegram/client/__init__.py
from .base_telegram_client import TelegramClient
from .mock_telegram_client import MockTelegramClientGateway

__all__ = ["TelegramClient", "MockTelegramClientGateway"]
