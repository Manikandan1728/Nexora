"""
app/integrations/telegram/services/session_restore.py

[MODIFIED] Part 2C
Safely loads a session bundle from persistence, decrypts it, and injects it into the Gateway.
"""

import logging
from sqlalchemy.orm import Session

from app.integrations.telegram.services.connection_registry import ConnectionRegistry
from app.integrations.telegram.security.session_secret_service import TelegramSessionSecretService
from app.integrations.telegram.security.session_errors import TelegramSessionDecryptionError
from app.integrations.telegram.db.orm_models import TelegramAccountORM

logger = logging.getLogger(__name__)


class TelegramSessionRestoreService:
    def __init__(
        self,
        registry: ConnectionRegistry,
        session_secret_service: TelegramSessionSecretService,
    ) -> None:
        self._registry = registry
        self._session_svc = session_secret_service

    async def restore_session_and_connect(
        self, account: TelegramAccountORM
    ) -> None:
        """
        Attempts to load a stored session and inject it into the client.
        If the session is corrupted, marks it as disconnected.
        """
        client = self._registry.get_client(account.id)
        
        if account.telethon_session_encrypted:
            try:
                # 1. Decrypt StringSession
                session_str = self._session_svc.decrypt_telethon_session(account.telethon_session_encrypted)
                
                # 2. Restore into client
                await client.restore_session(session_str)
                logger.info(f"Restored Telegram session for account {account.id}")
                
            except TelegramSessionDecryptionError as e:
                logger.error(f"Session restore failed for account {account.id} due to corruption: {e}")
            except Exception as e:
                logger.error(f"Unexpected error restoring session for {account.id}: {e}")
        else:
            logger.info(f"No existing Telegram session found for account {account.id}")
            
        # Ensure connected for phone login flow later
        await client.connect()
        if account.telethon_session_encrypted:
            is_auth = await client.is_authorized()
            if not is_auth:
                logger.warning(f"Session for {account.id} restored but not authorized. Requires login.")
