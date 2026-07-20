"""
app/integrations/telegram/client/mock_telegram_client.py

[MODIFIED] Part 2C
Mock implementation of the TelegramClientGateway interface.
Safe for tests and local development. Never contacts real Telegram servers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator, Any, Literal

from app.integrations.telegram.client.gateway import TelegramClientGateway

logger = logging.getLogger(__name__)

_FIXTURES_DIR = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "telegram"


class MockTelegramClientGateway(TelegramClientGateway):
    def __init__(
        self,
        fixtures_dir: Path | None = None,
        auth_state: str = "disconnected",
    ) -> None:
        self._fixtures_dir = fixtures_dir or _FIXTURES_DIR
        self._auth_state = auth_state
        self._connected = False
        self._session_data: str | None = None

    async def start_authentication(self, phone_number: str) -> dict[str, Any]:
        logger.info("MockTelegramClientGateway: start_authentication (mock, not logged)")
        self._auth_state = "waiting_code"
        return {"phone_code_hash": "mock_hash_12345", "status": "code_sent"}

    async def verify_code(self, code: str, phone_code_hash: str | None = None) -> bool | Literal["password_required"]:
        logger.info("MockTelegramClientGateway: verify_code (mock, not logged)")
        if code == "11111":
            self._auth_state = "waiting_password"
            return "password_required"
        if code == "00000":
            raise ValueError("TELEGRAM_CODE_INVALID")
            
        self._auth_state = "ready"
        self._session_data = "mock_session_string_valid"
        return True

    async def verify_password(self, password: str) -> bool:
        logger.info("MockTelegramClientGateway: verify_password (mock, not logged)")
        if password == "wrong":
            raise ValueError("TELEGRAM_PASSWORD_INVALID")
            
        self._auth_state = "ready"
        self._session_data = "mock_session_string_valid"
        return True

    async def is_authorized(self) -> bool:
        return self._auth_state == "ready"

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockTelegramClientGateway: connected (mock).")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockTelegramClientGateway: disconnected (mock).")

    async def log_out(self) -> None:
        self._auth_state = "disconnected"
        self._session_data = None
        self._connected = False
        logger.info("MockTelegramClientGateway: log_out (mock).")

    async def export_session(self) -> str | None:
        return self._session_data

    async def restore_session(self, session_data: str) -> None:
        self._session_data = session_data
        self._auth_state = "ready"
        logger.info("MockTelegramClientGateway: restore_session (mock).")

    async def download_file(self, file_id: str) -> str:
        return f"/mock/path/to/{file_id}"

    # Kept for compatibility with existing tests that might call this directly
    async def list_chats(self) -> list[dict]:
        """Return mock chat list derived from fixture file names."""
        chats = [
            {
                "chat_id": "tg_chat_anu_001",
                "title": "Anu",
                "chat_type": "private",
                "last_activity": "2026-07-13T18:50:00+05:30",
                "indexing_enabled": True,
                "indexing_enabled_at": "2026-07-13T18:00:00+05:30",
            },
            {
                "chat_id": "tg_chat_arun_001",
                "title": "Arun",
                "chat_type": "private",
                "last_activity": "2026-07-13T16:00:00+05:30",
                "indexing_enabled": True,
                "indexing_enabled_at": "2026-07-13T14:00:00+05:30",
            },
            {
                "chat_id": "tg_group_project_001",
                "title": "Project Team",
                "chat_type": "group",
                "last_activity": "2026-07-13T10:00:00+05:30",
                "indexing_enabled": True,
                "indexing_enabled_at": "2026-07-13T09:00:00+05:30",
            },
            {
                "chat_id": "tg_chat_disabled_001",
                "title": "Disabled Chat",
                "chat_type": "private",
                "last_activity": "2026-07-13T12:00:00+05:30",
                "indexing_enabled": False,
                "indexing_enabled_at": None,
            },
        ]
        return chats

    async def updates(self) -> AsyncIterator[dict]:
        if not self._fixtures_dir.exists():
            return

        fixture_files = sorted(self._fixtures_dir.glob("*.json"))
        for fixture_path in fixture_files:
            try:
                with open(fixture_path, encoding="utf-8") as f:
                    event = json.load(f)
                if set(event.keys()) <= {"_comment"}:
                    continue
                yield event
                await asyncio.sleep(0)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("MockTelegramClientGateway: failed to load fixture %s", fixture_path.name)
