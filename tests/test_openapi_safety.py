"""
tests/test_openapi_safety.py

[ADDITIVE] Part 2B — Mission 3.

Guards to ensure OpenAPI schema generation never leaks sensitive fields.
"""
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_openapi_schema_does_not_leak_secrets():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    schema_str = response.text

    # 1. No encrypted fields or keys should exist anywhere in the OpenAPI schema
    assert "phone_number_encrypted" not in schema_str
    assert "ciphertext" not in schema_str
    assert "session_reference_encrypted" not in schema_str
    assert "tdlib_database_key_encrypted" not in schema_str
    assert "tdlib_files_database_key_encrypted" not in schema_str
    assert "session_locator_encrypted" not in schema_str

    # 2. Check the components schema explicitly
    components = schema.get("components", {}).get("schemas", {})
    
    # PhoneRequest MUST have phone_number
    assert "PhoneRequest" in components
    assert "phone_number" in components["PhoneRequest"]["properties"]
    
    # TelegramAccountResponse MUST NOT have phone_number or phone_number_encrypted
    assert "TelegramAccountResponse" in components
    resp_props = components["TelegramAccountResponse"]["properties"]
    assert "phone_number_encrypted" not in resp_props
    assert "phone_number" not in resp_props
    assert "phone_number_masked" in resp_props

def test_openapi_schemas_for_endpoints():
    response = client.get("/openapi.json")
    schema = response.json()
    paths = schema.get("paths", {})

    # Check POST /integrations/telegram/auth/phone response
    phone_auth_resp = paths["/integrations/telegram/auth/phone"]["post"]["responses"]["200"]
    # We just ensure it doesn't leak
    assert "phone_number_encrypted" not in str(phone_auth_resp)

    # Check GET /integrations/telegram/accounts
    accounts_resp = paths["/integrations/telegram/accounts"]["get"]["responses"]["200"]
    assert "phone_number_encrypted" not in str(accounts_resp)
