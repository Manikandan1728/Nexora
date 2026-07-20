"""
api/services/telegram_auth_service.py

[MODIFIED] Part 2C
Application service responsible for handling phone-number submissions, OTP, and 2FA.
Maintains a secure in-memory temporary authentication transaction store.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
import uuid
from typing import Dict, Literal
from dataclasses import dataclass

from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.integrations.telegram.db.orm_models import TelegramAccountORM
from app.integrations.telegram.repositories.account_repo import TelegramAccountRepository
from app.integrations.telegram.security.errors import TelegramPhoneEncryptionError, TelegramPhoneNumberValidationError
from app.integrations.telegram.security.phone_secret_service import TelegramPhoneSecretService
from app.integrations.telegram.security.session_secret_service import TelegramSessionSecretService
from app.integrations.telegram.services.connection_registry import ConnectionRegistry
from api.exceptions import InvalidInputError, ProcessingError

logger = logging.getLogger(__name__)


@dataclass
class AuthTransaction:
    attempt_id: str
    owner_id: str
    account_id: str
    phone_code_hash: str
    expires_at: datetime


class TelegramPhoneSubmissionResult(BaseModel):
    status: str
    phone_number_masked: str
    telegram_account_id: str
    authentication_attempt_id: str | None = None


class AuthVerificationResult(BaseModel):
    status: str
    message: str
    authentication_attempt_id: str | None = None


# Secure in-memory store for ongoing auth transactions
_AUTH_TRANSACTIONS: Dict[str, AuthTransaction] = {}


class TelegramPhoneAuthorizationService:
    def __init__(
        self,
        phone_secret_service: TelegramPhoneSecretService,
        session_secret_service: TelegramSessionSecretService,
        account_repo: TelegramAccountRepository,
        registry: ConnectionRegistry,
        session: Session,
    ) -> None:
        self._phone_svc = phone_secret_service
        self._session_svc = session_secret_service
        self._account_repo = account_repo
        self._registry = registry
        self._session = session

    def _cleanup_expired_transactions(self) -> None:
        now = datetime.now(timezone.utc)
        expired_keys = [k for k, v in _AUTH_TRANSACTIONS.items() if v.expires_at < now]
        for k in expired_keys:
            del _AUTH_TRANSACTIONS[k]

    async def submit_phone_number(
        self,
        *,
        owner_id: str,
        raw_phone_number: str,
    ) -> TelegramPhoneSubmissionResult:
        self._cleanup_expired_transactions()
        
        try:
            ciphertext = self._phone_svc.encrypt_phone_number(raw_phone_number)
            masked_phone = self._phone_svc.get_masked_phone_number(ciphertext)
        except TelegramPhoneNumberValidationError as exc:
            raise InvalidInputError("The Telegram phone number is invalid. Ensure it is in international format (e.g., +1 234 567 8900).") from exc
        except TelegramPhoneEncryptionError as exc:
            logger.error("Phone encryption failed: %s", exc.safe_detail)
            raise ProcessingError("An internal error occurred during phone number submission.") from exc

        telegram_user_id = "mock_user_001"
        account = self._account_repo.get_owned_account(self._session, owner_id=owner_id, source_account_id=telegram_user_id)
        
        if not account:
            account = TelegramAccountORM(
                id=f"acc_{uuid.uuid4().hex[:12]}",
                owner_id=owner_id,
                telegram_user_id=telegram_user_id,
                authorization_status="waiting_code",
                is_active=True,
                phone_number_encrypted=ciphertext,
                connected_at=datetime.now(timezone.utc),
            )
        else:
            account.phone_number_encrypted = ciphertext
            account.authorization_status = "waiting_code"

        self._account_repo.upsert(self._session, account)
        self._session.commit()

        # Call Telethon to request the code
        client = self._registry.get_client(account.id)
        auth_res = await client.start_authentication(raw_phone_number)
        phone_code_hash = auth_res.get("phone_code_hash")
        
        if not phone_code_hash:
            raise ProcessingError("Failed to obtain phone_code_hash from Telegram.")

        attempt_id = f"auth_{uuid.uuid4().hex}"
        _AUTH_TRANSACTIONS[attempt_id] = AuthTransaction(
            attempt_id=attempt_id,
            owner_id=owner_id,
            account_id=account.id,
            phone_code_hash=phone_code_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
        )
        
        logger.info("Phone number submitted and code requested for owner=%r", owner_id)

        return TelegramPhoneSubmissionResult(
            status="waiting_code",
            phone_number_masked=masked_phone,
            telegram_account_id=account.telegram_user_id,
            authentication_attempt_id=attempt_id,
        )

    async def verify_code(
        self,
        *,
        owner_id: str,
        attempt_id: str,
        code: str,
    ) -> AuthVerificationResult:
        self._cleanup_expired_transactions()
        
        transaction = _AUTH_TRANSACTIONS.get(attempt_id)
        if not transaction or transaction.owner_id != owner_id:
            raise InvalidInputError("Authentication session expired or invalid. Please request a new code.")
            
        client = self._registry.get_client(transaction.account_id)
        result = await client.verify_code(code, transaction.phone_code_hash)
        
        account = self._account_repo.get_by_id(self._session, transaction.account_id)
        if not account:
            raise ProcessingError("Account not found.")

        if result == "password_required":
            account.authorization_status = "waiting_password"
            self._account_repo.upsert(self._session, account)
            self._session.commit()
            return AuthVerificationResult(
                status="waiting_password",
                message="Two-factor password required.",
                authentication_attempt_id=attempt_id
            )
            
        # Successfully authenticated
        session_str = await client.export_session()
        if session_str:
            account.telethon_session_encrypted = self._session_svc.encrypt_telethon_session(session_str)
        
        account.authorization_status = "ready"
        self._account_repo.upsert(self._session, account)
        self._session.commit()
        
        # Cleanup
        del _AUTH_TRANSACTIONS[attempt_id]
        
        return AuthVerificationResult(
            status="ready",
            message="Authorization successful.",
        )

    async def verify_password(
        self,
        *,
        owner_id: str,
        attempt_id: str,
        password: str,
    ) -> AuthVerificationResult:
        self._cleanup_expired_transactions()
        
        transaction = _AUTH_TRANSACTIONS.get(attempt_id)
        if not transaction or transaction.owner_id != owner_id:
            raise InvalidInputError("Authentication session expired or invalid. Please restart login.")
            
        client = self._registry.get_client(transaction.account_id)
        await client.verify_password(password)
        
        account = self._account_repo.get(self._session, transaction.account_id)
        if not account:
            raise ProcessingError("Account not found.")
            
        # Successfully authenticated
        session_str = await client.export_session()
        if session_str:
            account.telethon_session_encrypted = self._session_svc.encrypt_telethon_session(session_str)
            
        account.authorization_status = "ready"
        self._account_repo.upsert(self._session, account)
        self._session.commit()
        
        del _AUTH_TRANSACTIONS[attempt_id]
        
        return AuthVerificationResult(
            status="ready",
            message="Authorization successful.",
        )
