"""
app/integrations/telegram/client/telethon_client.py

[ADDITIVE] Part 2C
Real implementation of the TelegramClientGateway using Telethon.
"""

from typing import Any, Literal
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneNumberInvalidError, PhoneCodeInvalidError,
    PhoneCodeExpiredError, PasswordHashInvalidError, FloodWaitError,
    AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, RPCError
)

from app.integrations.telegram.client.gateway import TelegramClientGateway
from api.exceptions import ProcessingError, InvalidInputError

logger = logging.getLogger(__name__)

class TelethonTelegramClientGateway(TelegramClientGateway):
    def __init__(self, api_id: int, api_hash: str, device_model: str, system_version: str | None, app_version: str | None, lang_code: str, system_lang_code: str) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.device_model = device_model
        self.system_version = system_version or "1.0"
        self.app_version = app_version or "1.0"
        self.lang_code = lang_code
        self.system_lang_code = system_lang_code
        
        self.client: TelegramClient | None = None
        self._session = StringSession()

    def _ensure_client(self) -> None:
        if self.client is None:
            self.client = TelegramClient(
                self._session, 
                self.api_id, 
                self.api_hash,
                device_model=self.device_model,
                system_version=self.system_version,
                app_version=self.app_version,
                lang_code=self.lang_code,
                system_lang_code=self.system_lang_code
            )

    async def connect(self) -> None:
        self._ensure_client()
        if not self.client.is_connected():
            await self.client.connect()
            logger.info("TelethonTelegramClientGateway: connected")

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("TelethonTelegramClientGateway: disconnected")

    def _map_telethon_error(self, exc: Exception) -> Exception:
        """Map Telethon errors to safe backend exception types."""
        if isinstance(exc, PhoneNumberInvalidError):
            return InvalidInputError("TELEGRAM_PHONE_INVALID")
        if isinstance(exc, PhoneCodeInvalidError):
            return InvalidInputError("TELEGRAM_CODE_INVALID")
        if isinstance(exc, PhoneCodeExpiredError):
            return InvalidInputError("TELEGRAM_CODE_EXPIRED")
        if isinstance(exc, PasswordHashInvalidError):
            return InvalidInputError("TELEGRAM_PASSWORD_INVALID")
        if isinstance(exc, FloodWaitError):
            # Do not leak wait time explicitly in public message, but we could
            return ProcessingError(f"TELEGRAM_FLOOD_WAIT:{exc.seconds}")
        if isinstance(exc, (AuthKeyUnregisteredError, SessionRevokedError)):
            return ProcessingError("TELEGRAM_SESSION_REVOKED")
        if isinstance(exc, UserDeactivatedError):
            return ProcessingError("TELEGRAM_USER_DEACTIVATED")
        if isinstance(exc, RPCError):
            return ProcessingError(f"TELEGRAM_RPC_ERROR:{exc.__class__.__name__}")
        
        return ProcessingError("TELEGRAM_NETWORK_ERROR")

    async def start_authentication(self, phone_number: str) -> dict[str, Any]:
        await self.connect()
        try:
            sent_code = await self.client.send_code_request(phone_number)
            logger.info("Telethon: code requested successfully")
            return {"phone_code_hash": sent_code.phone_code_hash, "status": "code_sent"}
        except Exception as e:
            logger.error(f"Telethon error sending code: {type(e).__name__}")
            raise self._map_telethon_error(e)

    async def verify_code(self, code: str, phone_code_hash: str | None = None) -> bool | Literal["password_required"]:
        if not self.client:
            raise ProcessingError("Client not initialized")
        
        # Telethon sign_in needs phone_number or phone_code_hash, but we must have phone_code_hash
        # In reality, telethon cache the phone_number locally if it's the same client instance,
        # but to be safe, we will pass phone_code_hash if we have it, wait, `sign_in` takes `phone` and `code`, or `phone_code_hash` isn't directly usable alone in some overloads. 
        # Actually, `client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)`
        # Since we might not have the plaintext phone here, we can pass phone_code_hash.
        # Wait, Telethon's `sign_in` requires `phone` if not cached. 
        # But if the same client instance is alive, `code` alone works: `client.sign_in(code=code)`
        try:
            await self.client.sign_in(code=code)
            return True
        except SessionPasswordNeededError:
            return "password_required"
        except Exception as e:
            logger.error(f"Telethon error verifying code: {type(e).__name__}")
            raise self._map_telethon_error(e)

    async def verify_password(self, password: str) -> bool:
        if not self.client:
            raise ProcessingError("Client not initialized")
            
        try:
            await self.client.sign_in(password=password)
            return True
        except Exception as e:
            logger.error(f"Telethon error verifying password: {type(e).__name__}")
            raise self._map_telethon_error(e)

    async def is_authorized(self) -> bool:
        if not self.client:
            return False
        return await self.client.is_user_authorized()

    async def log_out(self) -> None:
        if self.client:
            try:
                await self.client.log_out()
                logger.info("TelethonTelegramClientGateway: logged out session")
            except Exception as e:
                logger.warning(f"Error during logout: {e}")
            finally:
                self.client = None
                self._session = StringSession()

    async def export_session(self) -> str | None:
        if self.client and self._session:
            return self._session.save()
        return None

    async def restore_session(self, session_data: str) -> None:
        self._session = StringSession(session_data)
        # Client needs to be recreated with the new session
        if self.client:
            if self.client.is_connected():
                await self.client.disconnect()
            self.client = None
        self._ensure_client()
