"""
tests/test_session_persistence.py

[ADDITIVE] Part 2C — Phases 21 & 24
Unit and integration tests for Session Persistence and Restore flows.
"""

import pytest
from unittest.mock import AsyncMock
from pydantic import SecretStr

from app.integrations.telegram.models.session_models import DecryptedTelegramSessionBundle, TelegramSessionStatus
from app.integrations.telegram.db.engine import get_session, create_all_tables, reset_engine, DatabaseSettings
from app.integrations.telegram.repositories.account_repo import SqliteTelegramAccountRepository
from app.integrations.telegram.security.session_secret_service import TelegramSessionSecretService
from app.integrations.telegram.services.session_persistence import TelegramSessionPersistenceService
from app.integrations.telegram.services.session_restore import TelegramSessionRestoreService
from app.integrations.telegram.client.base_telegram_client import TelegramClientBootstrapConfig
from app.security.secrets.factory import create_secret_store
import base64

@pytest.fixture
def db_session(tmp_path):
    reset_engine()
    db_path = str(tmp_path / "test_session.db")
    settings = DatabaseSettings(db_path=db_path)
    create_all_tables(settings)
    session = get_session(settings)
    yield session
    session.close()


@pytest.fixture
def persistence_service():
    dummy_key = base64.urlsafe_b64encode(b"00000000000000000000000000000000").decode("ascii")
    store = create_secret_store("environment", raw_key=dummy_key, key_id="test")
    secret_svc = TelegramSessionSecretService(store)
    repo = SqliteTelegramAccountRepository()
    return TelegramSessionPersistenceService(secret_svc, repo)


def test_store_and_load_session_bundle(db_session, persistence_service: TelegramSessionPersistenceService):
    owner_id = "test_owner"
    user_id = "tg_user_123"

    decrypted = DecryptedTelegramSessionBundle(
        session_reference=SecretStr("my-opaque-reference"),
        tdlib_database_key=SecretStr("super-secret-db-key")
    )

    # Store
    account = persistence_service.store_session_bundle(
        db_session, owner_id, user_id, decrypted
    )
    db_session.commit()

    assert account.session_status == "available"
    assert account.session_reference_encrypted.startswith("nexora:v1:")
    assert account.tdlib_database_key_encrypted.startswith("nexora:v1:")
    assert account.tdlib_files_database_key_encrypted is None

    # Load
    loaded = persistence_service.load_session_bundle(db_session, owner_id, user_id)
    assert loaded is not None
    assert loaded.session_reference.get_secret_value() == "my-opaque-reference"
    assert loaded.tdlib_database_key.get_secret_value() == "super-secret-db-key"
    assert loaded.tdlib_files_database_key is None


def test_clear_session_bundle(db_session, persistence_service: TelegramSessionPersistenceService):
    owner_id = "test_owner"
    user_id = "tg_user_123"

    decrypted = DecryptedTelegramSessionBundle(session_reference=SecretStr("ref"))
    persistence_service.store_session_bundle(db_session, owner_id, user_id, decrypted)
    db_session.commit()

    persistence_service.clear_session_bundle(db_session, owner_id, user_id)
    db_session.commit()

    loaded = persistence_service.load_session_bundle(db_session, owner_id, user_id)
    assert loaded is None

    repo = SqliteTelegramAccountRepository()
    account = repo.get_owned_account(db_session, owner_id, user_id)
    assert account.session_status == "absent"
    assert account.session_reference_encrypted is None


@pytest.mark.asyncio
async def test_session_restore_service_success(db_session, persistence_service):
    # Setup stored session
    owner_id = "test_owner"
    user_id = "tg_user_123"
    repo = SqliteTelegramAccountRepository()
    from app.integrations.telegram.db.orm_models import TelegramAccountORM
    account = TelegramAccountORM(id="acc_1", owner_id=owner_id, telegram_user_id=user_id)
    repo.upsert(db_session, account)
    
    secret_svc = persistence_service._secret_service
    encrypted = secret_svc.encrypt_telethon_session("my-string-session")
    account.telethon_session_encrypted = encrypted
    repo.upsert(db_session, account)
    db_session.commit()

    # Mock client and registry
    from unittest.mock import MagicMock
    mock_client = AsyncMock()
    mock_registry = MagicMock()
    mock_registry.get_client.return_value = mock_client
    
    restore_svc = TelegramSessionRestoreService(mock_registry, secret_svc)
    await restore_svc.restore_session_and_connect(account)

    mock_client.restore_session.assert_called_once_with("my-string-session")
    mock_client.connect.assert_called_once()
    mock_client.is_authorized.assert_called_once()


@pytest.mark.asyncio
async def test_corrupted_ciphertext_policy_on_restore(db_session, persistence_service):
    owner_id = "test_owner"
    user_id = "tg_user_123"
    repo = SqliteTelegramAccountRepository()
    from app.integrations.telegram.db.orm_models import TelegramAccountORM
    account = TelegramAccountORM(id="acc_2", owner_id=owner_id, telegram_user_id=user_id)
    account.telethon_session_encrypted = "nexora:v1:corrupted-data"
    repo.upsert(db_session, account)
    db_session.commit()

    secret_svc = persistence_service._secret_service
    from unittest.mock import MagicMock
    mock_client = AsyncMock()
    mock_registry = MagicMock()
    mock_registry.get_client.return_value = mock_client

    restore_svc = TelegramSessionRestoreService(mock_registry, secret_svc)
    await restore_svc.restore_session_and_connect(account)

    mock_client.restore_session.assert_not_called()
    mock_client.connect.assert_called_once()
