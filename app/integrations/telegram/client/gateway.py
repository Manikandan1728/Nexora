"""
app/integrations/telegram/client/gateway.py

[ADDITIVE] Part 2C
Defines the `TelegramClientGateway` protocol, the unified boundary for mock and real
Telegram client operations. Ensures backend routes/services never depend directly on Telethon.
"""

from typing import Protocol, Any, Literal


class TelegramClientGateway(Protocol):
    async def start_authentication(self, phone_number: str) -> dict[str, Any]:
        """
        Request an authentication code.
        Returns a dict containing 'phone_code_hash' (required by Telegram) or status info.
        """
        ...

    async def verify_code(self, code: str, phone_code_hash: str | None = None) -> bool | Literal["password_required"]:
        """
        Verify the OTP code.
        Returns True if authenticated, or 'password_required' if 2FA is needed.
        """
        ...

    async def verify_password(self, password: str) -> bool:
        """
        Verify the 2FA password.
        Returns True if authenticated.
        """
        ...

    async def is_authorized(self) -> bool:
        """Check if the current session is authorized."""
        ...

    async def connect(self) -> None:
        """Connect the client to the Telegram network."""
        ...

    async def disconnect(self) -> None:
        """Disconnect the client from the Telegram network."""
        ...

    async def log_out(self) -> None:
        """Log out the current session, invalidating it."""
        ...

    async def export_session(self) -> str | None:
        """Export the current session state as a string (e.g. StringSession)."""
        ...

    async def restore_session(self, session_data: str) -> None:
        """Restore the client session from string data."""
        ...
