"""
app/integrations/telegram/client/base_telegram_client.py

[ADDITIVE] — New file. Defines the TelegramClient Protocol interface.

Both MockTelegramClient (current) and TDLibTelegramClient (future Phase 15)
implement this interface. The application only depends on this interface —
never on a concrete implementation.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable
from pydantic import BaseModel, SecretStr
from typing import Optional

class TelegramClientBootstrapConfig(BaseModel):
    """
    Configuration payload passed to the client during bootstrap.
    Contains decrypted session secrets safely wrapped in SecretStr.
    """
    session_reference: Optional[SecretStr] = None
    tdlib_database_key: Optional[SecretStr] = None
    tdlib_files_database_key: Optional[SecretStr] = None
    session_locator: Optional[SecretStr] = None


@runtime_checkable
class TelegramClient(Protocol):
    """
    Abstract interface for a Telegram client backend.

    Current implementation: MockTelegramClient
    Future implementation:  TDLibTelegramClient (Phase 15)

    The application layer (API routes, ingestion services) depends on this
    interface only — never on TDLib or any other backend directly. Switching
    from Mock to TDLib requires only a config change, not code changes.
    """

    async def configure_session(self, config: TelegramClientBootstrapConfig) -> None:
        """
        Inject decrypted session secrets into the client before connection.
        Must be called prior to connect() if a session exists.
        """
        ...

    async def clear_session(self) -> None:
        """
        Instruct the client to wipe local session state/files.
        Used during logout or account deletion.
        """
        ...

    async def connect(self) -> None:
        """Establish the Telegram client connection."""
        ...

    async def disconnect(self) -> None:
        """Disconnect and release resources."""
        ...

    async def get_authorization_state(self) -> str:
        """
        Return the current authorization state string.
        One of: disconnected, waiting_phone, waiting_code,
                waiting_password, ready, closed, error.
        """
        ...

    async def submit_phone_number(self, phone_number: str) -> None:
        """
        Submit a phone number to begin Telegram authorization.
        Never log or store the phone number in plaintext.
        """
        ...

    async def submit_code(self, code: str) -> None:
        """
        Submit the OTP verification code.
        Never persist the code after this call.
        """
        ...

    async def submit_password(self, password: str) -> None:
        """
        Submit the two-step verification password.
        Never persist the password.
        """
        ...

    async def list_chats(self) -> list[dict]:
        """
        Return a list of chat info dicts for the connected account.
        Each dict contains at minimum: chat_id, title, chat_type.
        """
        ...

    async def updates(self) -> AsyncIterator[dict]:
        """
        Yield incoming Telegram update events as dicts.
        Runs indefinitely until disconnect() is called.
        """
        ...

    async def download_file(self, file_id: str) -> str:
        """
        Download a Telegram file and return its local path.
        Returns a path relative to the media root.
        """
        ...
