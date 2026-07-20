"""
tests/test_session_secret_service.py

[ADDITIVE] Part 2C — Phase 21: Unit tests for TelegramSessionSecretService.
Ensures double-encryption prevention and strict context bounds.
"""

import pytest
from app.integrations.telegram.security.session_secret_service import TelegramSessionSecretService
from app.integrations.telegram.security.session_errors import (
    TelegramSessionEncryptionError,
    TelegramSessionDecryptionError,
)
from app.security.secrets.base import SecretStore
from app.security.secrets.factory import create_secret_store
import base64

@pytest.fixture
def store() -> SecretStore:
    dummy_key = base64.urlsafe_b64encode(b"00000000000000000000000000000000").decode("ascii")
    return create_secret_store("environment", raw_key=dummy_key, key_id="test")


@pytest.fixture
def service(store) -> TelegramSessionSecretService:
    return TelegramSessionSecretService(store)


def test_session_reference_encryption(service: TelegramSessionSecretService):
    plaintext = "my-secret-session-reference-123"
    ciphertext = service.encrypt_session_reference(plaintext)
    
    assert ciphertext != plaintext
    assert service.is_encrypted_payload(ciphertext)
    assert ciphertext.startswith("nexora:v1:")

    decrypted = service.decrypt_session_reference(ciphertext)
    assert decrypted == plaintext


def test_double_encryption_prevented(service: TelegramSessionSecretService):
    plaintext = "session-123"
    ciphertext = service.encrypt_session_reference(plaintext)
    
    with pytest.raises(TelegramSessionEncryptionError, match="Double-encryption is prevented"):
        service.encrypt_session_reference(ciphertext)


def test_context_binding(service: TelegramSessionSecretService):
    """
    Encrypting as session_reference and trying to decrypt as tdlib_database_key
    must fail because of differing contexts.
    """
    plaintext = "shared-secret-value"
    ciphertext = service.encrypt_session_reference(plaintext)

    with pytest.raises(TelegramSessionDecryptionError):
        # A mismatch in context fails AES-GCM decryption
        service.decrypt_tdlib_database_key(ciphertext)


def test_empty_values(service: TelegramSessionSecretService):
    with pytest.raises(TelegramSessionEncryptionError):
        service.encrypt_session_reference("")
    
    with pytest.raises(TelegramSessionDecryptionError):
        service.decrypt_session_reference("")


def test_invalid_ciphertext_format(service: TelegramSessionSecretService):
    with pytest.raises(TelegramSessionDecryptionError, match="Value is not an encrypted payload"):
        service.decrypt_session_reference("invalid-format-not-nexora:v1:")
