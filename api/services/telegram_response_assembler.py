"""
api/services/telegram_response_assembler.py

[ADDITIVE] Part 2B — Mission 3.

Safely maps TelegramAccountORM objects to public API response models.
Enforces the Corrupted Ciphertext Policy (Phase 6):
- If decryption fails, returns a degraded safe state (error + null phone).
- Never returns plaintext.
- Never returns ciphertext.
"""
from __future__ import annotations

import logging

from app.integrations.telegram.db.orm_models import TelegramAccountORM
from app.integrations.telegram.security.errors import TelegramPhoneDecryptionError
from app.integrations.telegram.security.phone_secret_service import TelegramPhoneSecretService
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TelegramAccountResponse(BaseModel):
    """
    Public API response for a Telegram account.
    Never exposes encrypted phone numbers or session keys.
    """
    telegram_account_id: str
    display_name: str | None = None
    username: str | None = None
    authorization_status: str
    session_status: str
    phone_number_masked: str | None = None


class TelegramAccountResponseAssembler:
    """Assembles safe public responses from ORM models."""

    def __init__(self, phone_secret_service: TelegramPhoneSecretService) -> None:
        self._phone_svc = phone_secret_service

    def to_response(self, account: TelegramAccountORM) -> TelegramAccountResponse:
        """
        Map ORM model to API response, decrypting and masking the phone number safely.
        """
        masked_phone = None
        auth_status = account.authorization_status

        if account.phone_number_encrypted:
            try:
                masked_phone = self._phone_svc.get_masked_phone_number(account.phone_number_encrypted)
            except TelegramPhoneDecryptionError as exc:
                logger.warning(
                    "Corrupted phone ciphertext for account %s: %s",
                    account.id,
                    exc.safe_detail,
                )
                auth_status = "error"
                # Degraded safe state: masked_phone remains None

        return TelegramAccountResponse(
            telegram_account_id=account.telegram_user_id,
            display_name=account.display_name,
            username=account.username,
            authorization_status=auth_status,
            session_status=account.session_status,
            phone_number_masked=masked_phone,
        )
