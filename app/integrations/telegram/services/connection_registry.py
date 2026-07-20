"""
app/integrations/telegram/services/connection_registry.py

[ADDITIVE] Part 2C
Manages TelegramClientGateway instances by account_id to prevent redundant connections
and ensure safe isolation between users.
"""

import logging
from typing import Dict
from app.integrations.telegram.client.gateway import TelegramClientGateway
from app.integrations.telegram.client.mock_telegram_client import MockTelegramClientGateway
from app.integrations.telegram.client.telethon_client import TelethonTelegramClientGateway
from api.config import APISettings

logger = logging.getLogger(__name__)

class ConnectionRegistry:
    """Manages active TelegramClientGateway instances."""
    
    def __init__(self, settings: APISettings) -> None:
        self._settings = settings
        self._clients: Dict[str, TelegramClientGateway] = {}

    def get_client(self, account_id: str) -> TelegramClientGateway:
        """Get or lazily create a client for a specific account."""
        if account_id not in self._clients:
            if self._settings.telegram_mode == "real":
                self._clients[account_id] = TelethonTelegramClientGateway(
                    api_id=self._settings.telegram_api_id,
                    api_hash=self._settings.telegram_api_hash,
                    device_model=self._settings.telegram_device_model,
                    system_version=self._settings.telegram_system_version,
                    app_version=self._settings.telegram_app_version,
                    lang_code=self._settings.telegram_lang_code,
                    system_lang_code=self._settings.telegram_system_lang_code
                )
                logger.info(f"Created real Telethon client for account {account_id}")
            else:
                self._clients[account_id] = MockTelegramClientGateway()
                logger.info(f"Created Mock client for account {account_id}")
        
        return self._clients[account_id]

    def remove_client(self, account_id: str) -> None:
        """Remove a client from the registry, usually after logout/disconnect."""
        if account_id in self._clients:
            del self._clients[account_id]
            
    async def disconnect_all(self) -> None:
        """Disconnect all active clients (e.g. during shutdown)."""
        for acc_id, client in self._clients.items():
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting client for {acc_id}: {e}")
        self._clients.clear()
