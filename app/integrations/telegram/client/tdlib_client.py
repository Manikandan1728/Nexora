"""
app/integrations/telegram/client/tdlib_client.py

[ADDITIVE] — Stub only. NOT wired into the active runtime path.
The application config always defaults to MockTelegramClient.

This stub documents the future TDLibTelegramClient interface contract.
It raises NotImplementedError on every call to prevent accidental use
before Phase 15 implementation is complete.

To activate: set NEXORA_TELEGRAM_CLIENT=tdlib in the environment.
Default is NEXORA_TELEGRAM_CLIENT=mock.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from app.integrations.telegram.client.base_telegram_client import TelegramClientBootstrapConfig

logger = logging.getLogger(__name__)


class TDLibTelegramClient:
    """
    [STUB — NOT IMPLEMENTED]

    Future TDLib-based implementation of the TelegramClient interface.
    All methods raise NotImplementedError until Phase 15.

    When implemented, this class will:
    - Use python-telegram (or pytdbot) to wrap the native TDLib binary.
    - Handle TDLib authorization flow securely.
    - Stream incoming updates via TDLib's update handler.
    - Download files via TDLib's downloadFile request.
    - Never expose OTP codes, 2FA passwords, or session keys in logs.
    """

    def __init__(self) -> None:
        logger.warning(
            "TDLibTelegramClient instantiated but is not yet implemented. "
            "Use MockTelegramClient instead."
        )

    async def configure_session(self, config: TelegramClientBootstrapConfig) -> None:
        raise NotImplementedError("TDLibTelegramClient.configure_session() not implemented.")

    async def clear_session(self) -> None:
        raise NotImplementedError("TDLibTelegramClient.clear_session() not implemented.")

    async def connect(self) -> None:
        raise NotImplementedError(
            "TDLibTelegramClient is not yet implemented. "
            "Set NEXORA_TELEGRAM_CLIENT=mock to use MockTelegramClient."
        )

    async def disconnect(self) -> None:
        raise NotImplementedError("TDLibTelegramClient.disconnect() not implemented.")

    async def get_authorization_state(self) -> str:
        raise NotImplementedError(
            "TDLibTelegramClient.get_authorization_state() not implemented."
        )

    async def submit_phone_number(self, phone_number: str) -> None:
        raise NotImplementedError(
            "TDLibTelegramClient.submit_phone_number() not implemented."
        )

    async def submit_code(self, code: str) -> None:
        raise NotImplementedError(
            "TDLibTelegramClient.submit_code() not implemented."
        )

    async def submit_password(self, password: str) -> None:
        raise NotImplementedError(
            "TDLibTelegramClient.submit_password() not implemented."
        )

    async def list_chats(self) -> list[dict]:
        raise NotImplementedError(
            "TDLibTelegramClient.list_chats() not implemented."
        )

    async def updates(self) -> AsyncIterator[dict]:
        raise NotImplementedError(
            "TDLibTelegramClient.updates() not implemented."
        )
        yield {}  # type: ignore[misc]  # makes this an async generator

    async def download_file(self, file_id: str) -> str:
        raise NotImplementedError(
            "TDLibTelegramClient.download_file() not implemented."
        )
