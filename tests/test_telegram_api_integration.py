"""
tests/test_telegram_api_integration.py

[ADDITIVE] Part 2B — Mission 3.

Integration tests for Telegram phone-number endpoints.
Tests verify API payloads, safety boundaries, and DB states.
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from app.integrations.telegram.db.engine import get_session, DatabaseSettings
from app.integrations.telegram.repositories.account_repo import SqliteTelegramAccountRepository
from api.dependencies import get_db_session

# Test dependencies override to use an in-memory database
def override_get_db_session():
    settings = DatabaseSettings(db_path=":memory:")
    from app.integrations.telegram.db.orm_models import Base
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()

app.dependency_overrides[get_db_session] = override_get_db_session

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    # Since each route call will open a new session in TestClient with the override,
    # it actually re-initializes an in-memory DB per request (which is fine for these isolated tests).
    # Wait, SQLite :memory: resets per connection. We need a shared connection or just let it reset.
    # We will use a unique file-based memory DB to share state across requests in the same test.
    shared_engine = None
    from app.integrations.telegram.db.orm_models import Base
    from sqlalchemy import create_engine, StaticPool
    
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    
    def get_shared_session():
        from sqlalchemy.orm import sessionmaker
        session = sessionmaker(bind=engine)()
        try:
            yield session
        finally:
            session.close()
            
    app.dependency_overrides[get_db_session] = get_shared_session
    yield
    engine.dispose()
    app.dependency_overrides.clear()


def test_valid_phone_submission_and_status():
    # Test 1: Valid submission
    resp = client.post(
        "/integrations/telegram/auth/phone",
        json={"owner_id": "test_owner", "phone_number": "+91 98765 43210"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "waiting_code"
    assert data["phone_number_masked"] == "+91 ******3210"
    assert "phone_number_encrypted" not in data
    assert "phone_number" not in data
    
    # Test 4: Status response
    status_resp = client.get("/integrations/telegram/status?owner_id=test_owner")
    assert status_resp.status_code == 200
    sdata = status_resp.json()
    assert sdata["authorization_status"] == "waiting_code"
    assert sdata["account"]["phone_number_masked"] == "+91 ******3210"
    assert "phone_number_encrypted" not in str(sdata)

def test_invalid_phone_submission():
    # Test 2: Invalid submission
    resp = client.post(
        "/integrations/telegram/auth/phone",
        json={"owner_id": "test_owner", "phone_number": "not-a-number"}
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"] == "invalid_input"
    assert "not-a-number" not in data["message"]  # Raw input never echoed

def test_update_existing_account():
    # Test 3: Update existing
    client.post(
        "/integrations/telegram/auth/phone",
        json={"owner_id": "test_owner", "phone_number": "+1 202 555 0100"}
    )
    
    resp2 = client.post(
        "/integrations/telegram/auth/phone",
        json={"owner_id": "test_owner", "phone_number": "+44 7700 900000"}
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["phone_number_masked"] == "+44 ******0000"

def test_list_accounts():
    # Test 5: Account list
    client.post(
        "/integrations/telegram/auth/phone",
        json={"owner_id": "owner_abc", "phone_number": "+1 202 555 0100"}
    )
    
    resp = client.get("/integrations/telegram/accounts?owner_id=owner_abc")
    assert resp.status_code == 200
    accounts = resp.json()
    assert len(accounts) == 1
    assert accounts[0]["phone_number_masked"] == "+1 ******0100"
    assert "phone_number_encrypted" not in str(accounts)

def test_disconnect_and_delete_account():
    # Setup
    client.post(
        "/integrations/telegram/auth/phone",
        json={"owner_id": "owner_del", "phone_number": "+1 202 555 0100"}
    )
    
    # Test 7: Disconnect (temporary)
    resp = client.post("/integrations/telegram/disconnect", json={"owner_id": "owner_del"})
    assert resp.status_code == 200
    
    # Verify account still has phone
    status_resp = client.get("/integrations/telegram/status?owner_id=owner_del")
    assert status_resp.json()["account"]["phone_number_masked"] == "+1 ******0100"
    assert status_resp.json()["authorization_status"] == "disconnected"
    
    # Test 8: Delete Account (explicit)
    resp_del = client.delete("/integrations/telegram/account?owner_id=owner_del")
    assert resp_del.status_code == 200
    
    # Verify phone data is nulled
    status_resp2 = client.get("/integrations/telegram/status?owner_id=owner_del")
    assert status_resp2.json()["account"]["phone_number_masked"] is None
