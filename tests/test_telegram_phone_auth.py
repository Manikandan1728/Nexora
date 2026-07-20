"""
tests/test_telegram_phone_auth.py

[ADDITIVE] Part 2B — Mission 3.

Unit tests for TelegramPhoneAuthorizationService and TelegramAccountResponseAssembler.
"""
import pytest
from app.integrations.telegram.db.engine import get_session, DatabaseSettings
from app.integrations.telegram.repositories.account_repo import SqliteTelegramAccountRepository
from app.integrations.telegram.security.phone_secret_service import TelegramPhoneSecretService
from app.integrations.telegram.security.errors import TelegramPhoneDecryptionError
from app.security.secrets.in_memory import InMemorySecretStore
from api.services.telegram_auth_service import TelegramPhoneAuthorizationService
from api.services.telegram_response_assembler import TelegramAccountResponseAssembler
from api.exceptions import InvalidInputError, ProcessingError

@pytest.fixture
def secret_store():
    return InMemorySecretStore()

@pytest.fixture
def phone_service(secret_store):
    return TelegramPhoneSecretService(secret_store)

@pytest.fixture
def assembler(phone_service):
    return TelegramAccountResponseAssembler(phone_service)

@pytest.fixture
def session():
    # Use memory db for isolated testing
    settings = DatabaseSettings(db_path=":memory:")
    from app.integrations.telegram.db.orm_models import Base
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=engine)()

@pytest.fixture
def auth_service(phone_service, session):
    from unittest.mock import MagicMock, AsyncMock
    repo = SqliteTelegramAccountRepository()
    session_svc = MagicMock()
    mock_client = AsyncMock()
    mock_client.start_authentication.return_value = {"status": "waiting_code", "phone_code_hash": "mock"}
    registry = MagicMock()
    registry.get_client.return_value = mock_client
    return TelegramPhoneAuthorizationService(
        phone_secret_service=phone_service,
        session_secret_service=session_svc,
        account_repo=repo,
        registry=registry,
        session=session
    )


def test_auth_service_valid_phone(auth_service, session):
    import asyncio
    result = asyncio.run(auth_service.submit_phone_number(owner_id="owner_1", raw_phone_number="+91 98765 43210"))
    
    assert result.status == "waiting_code"
    assert result.phone_number_masked == "+91 ******3210"
    
    # Check DB
    repo = SqliteTelegramAccountRepository()
    account = repo.get_owned_account(session, owner_id="owner_1", source_account_id=result.telegram_account_id)
    assert account is not None
    assert account.phone_number_encrypted.startswith("nexora:v1:")
    assert "+919876543210" not in account.phone_number_encrypted

def test_auth_service_invalid_phone(auth_service):
    import asyncio
    with pytest.raises(InvalidInputError) as exc:
        asyncio.run(auth_service.submit_phone_number(owner_id="owner_1", raw_phone_number="not-a-number"))
    
    assert "Telegram phone number is invalid" in exc.value.message
    # Ensure raw input is not in exception message
    assert "not-a-number" not in exc.value.message

def test_assembler_valid_account(assembler, phone_service):
    ciphertext = phone_service.encrypt_phone_number("+91 98765 43210")
    from app.integrations.telegram.db.orm_models import TelegramAccountORM
    account = TelegramAccountORM(
        id="acc_1", owner_id="owner_1", telegram_user_id="user_1",
        authorization_status="waiting_code", session_status="absent", phone_number_encrypted=ciphertext
    )
    
    resp = assembler.to_response(account)
    assert resp.telegram_account_id == "user_1"
    assert resp.authorization_status == "waiting_code"
    assert resp.phone_number_masked == "+91 ******3210"

def test_assembler_corrupted_ciphertext(assembler):
    from app.integrations.telegram.db.orm_models import TelegramAccountORM
    account = TelegramAccountORM(
        id="acc_1", owner_id="owner_1", telegram_user_id="user_1",
        authorization_status="waiting_code", session_status="absent", phone_number_encrypted="nexora:v1:corrupteddata"
    )
    
    resp = assembler.to_response(account)
    # Fallback degraded state
    assert resp.authorization_status == "error"
    assert resp.phone_number_masked is None
