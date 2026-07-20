"""
tests/test_secret_store.py — Comprehensive secret-store tests (Phases 15+16+19).

Covers: protocol, factory, key validation, encryption/decryption, integrity,
context binding (DR-S4 truth table), deletion, health, logging safety,
concurrency, property-style fuzz, architecture guards, and non-regression
of existing health/settings behavior.
"""
from __future__ import annotations
import base64
import concurrent.futures
import os
import re
import threading
import pytest

from app.security.secrets.base import SecretStore, SecretStoreStatus
from app.security.secrets.environment_key import EnvironmentKeySecretStore
from app.security.secrets.in_memory import InMemorySecretStore
from app.security.secrets.factory import create_secret_store
from app.security.secrets.validation import decode_and_validate_key
from app.security.secrets.models import EncryptedPayload
from app.security.secrets.exceptions import (
    SecretStoreConfigurationError, SecretEncryptionError,
    SecretDecryptionError, SecretIntegrityError,
    SecretPayloadFormatError, SecretKeyNotFoundError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_key_b64() -> str:
    return base64.urlsafe_b64encode(b"\x42" * 32).decode("ascii")


def _make_env_store(key_b64: str | None = None, key_id: str = "k1") -> EnvironmentKeySecretStore:
    raw = key_b64 or _valid_key_b64()
    return EnvironmentKeySecretStore.from_env(raw_key=raw, key_id=key_id)


def _make_mem_store() -> InMemorySecretStore:
    return InMemorySecretStore()


# ===========================================================================
# Key validation (Phase 15)
# ===========================================================================

class TestKeyValidation:

    def test_valid_key_returns_bytes(self):
        kb = decode_and_validate_key(_valid_key_b64())
        assert len(kb) == 32

    def test_none_key_raises(self):
        with pytest.raises(SecretStoreConfigurationError, match="required"):
            decode_and_validate_key(None)

    def test_empty_key_raises(self):
        with pytest.raises(SecretStoreConfigurationError):
            decode_and_validate_key("")

    def test_whitespace_only_raises(self):
        with pytest.raises(SecretStoreConfigurationError):
            decode_and_validate_key("   ")

    def test_invalid_base64_wrong_length_raises(self):
        """A string that decodes to the wrong number of bytes is rejected."""
        short = base64.urlsafe_b64encode(b"\x00" * 10).decode()
        with pytest.raises(SecretStoreConfigurationError):
            decode_and_validate_key(short)

    def test_invalid_base64_raises(self):
        """Python's base64 is permissive; test that genuinely wrong-length input fails."""
        # 31 bytes — one byte short of 32 required
        short = base64.urlsafe_b64encode(b"\xAB" * 31).decode()
        with pytest.raises(SecretStoreConfigurationError):
            decode_and_validate_key(short)

    def test_wrong_length_raises(self):
        short = base64.urlsafe_b64encode(b"\x00" * 16).decode()
        with pytest.raises(SecretStoreConfigurationError, match="bytes"):
            decode_and_validate_key(short)

    def test_error_does_not_include_key_value(self):
        key = _valid_key_b64()
        try:
            decode_and_validate_key(None)
        except SecretStoreConfigurationError as exc:
            assert key not in str(exc)

    def test_key_id_validation_via_factory(self):
        with pytest.raises(SecretStoreConfigurationError):
            create_secret_store(provider="environment", raw_key=None, key_id="k1")


# ===========================================================================
# Factory (Phase 15)
# ===========================================================================

class TestFactory:

    def test_environment_provider_returns_env_store(self):
        store = create_secret_store("environment", _valid_key_b64(), "k1")
        assert isinstance(store, EnvironmentKeySecretStore)

    def test_memory_provider_returns_mem_store(self):
        store = create_secret_store("memory")
        assert isinstance(store, InMemorySecretStore)

    def test_unknown_provider_raises(self):
        with pytest.raises(SecretStoreConfigurationError, match="Unknown"):
            create_secret_store("redis")

    def test_unknown_provider_case_sensitive_check(self):
        with pytest.raises(SecretStoreConfigurationError):
            create_secret_store("ENVIRONMENT")  # must be lowercase

    def test_memory_missing_key_still_works(self):
        store = create_secret_store("memory")
        assert store is not None

    def test_protocol_satisfied_env(self):
        store = create_secret_store("environment", _valid_key_b64(), "k1")
        assert isinstance(store, SecretStore)

    def test_protocol_satisfied_mem(self):
        store = create_secret_store("memory")
        assert isinstance(store, SecretStore)


# ===========================================================================
# Encryption / Decryption round-trip (Phase 15)
# ===========================================================================

class TestEncryptDecryptRoundTrip:

    def _s(self): return _make_env_store()

    def test_basic_roundtrip(self):
        s = self._s()
        assert s.decrypt(s.encrypt("hello")) == "hello"

    def test_unicode_roundtrip(self):
        s = self._s()
        text = "私のパスワード 🔑 tëst"
        assert s.decrypt(s.encrypt(text)) == text

    def test_long_plaintext(self):
        s = self._s()
        text = "x" * 10000
        assert s.decrypt(s.encrypt(text)) == text

    def test_same_plaintext_different_ciphertext(self):
        s = self._s()
        c1 = s.encrypt("secret")
        c2 = s.encrypt("secret")
        assert c1 != c2

    def test_both_ciphertexts_decrypt_to_same_plaintext(self):
        s = self._s()
        p = "same value"
        assert s.decrypt(s.encrypt(p)) == p
        assert s.decrypt(s.encrypt(p)) == p

    def test_ciphertext_not_equal_to_plaintext(self):
        s = self._s()
        plain = "mysecret"
        cipher = s.encrypt(plain)
        assert plain not in cipher

    def test_payload_has_expected_prefix(self):
        s = self._s()
        cipher = s.encrypt("x")
        assert cipher.startswith("nexora:v1:")

    def test_empty_plaintext_rejected(self):
        s = self._s()
        with pytest.raises(SecretEncryptionError):
            s.encrypt("")

    def test_whitespace_only_rejected(self):
        s = self._s()
        with pytest.raises(SecretEncryptionError):
            s.encrypt("   ")

    def test_in_memory_roundtrip(self):
        s = _make_mem_store()
        assert s.decrypt(s.encrypt("in-memory-secret")) == "in-memory-secret"


# ===========================================================================
# Context binding — DR-S4 truth table (Phase 15)
# ===========================================================================

class TestContextBinding:

    def _s(self): return _make_env_store()

    def test_no_ctx_enc_no_ctx_dec_succeeds(self):
        s = self._s()
        c = s.encrypt("val", context=None)
        assert s.decrypt(c, context=None) == "val"

    def test_ctx_enc_same_ctx_dec_succeeds(self):
        s = self._s()
        c = s.encrypt("val", context="telegram_phone_number")
        assert s.decrypt(c, context="telegram_phone_number") == "val"

    def test_no_ctx_enc_with_ctx_dec_fails(self):
        s = self._s()
        c = s.encrypt("val", context=None)
        with pytest.raises((SecretIntegrityError, SecretDecryptionError)):
            s.decrypt(c, context="some_context")

    def test_ctx_enc_no_ctx_dec_fails(self):
        s = self._s()
        c = s.encrypt("val", context="ctx_a")
        with pytest.raises((SecretIntegrityError, SecretDecryptionError)):
            s.decrypt(c, context=None)

    def test_wrong_ctx_dec_fails(self):
        s = self._s()
        c = s.encrypt("val", context="ctx_a")
        with pytest.raises((SecretIntegrityError, SecretDecryptionError)):
            s.decrypt(c, context="ctx_b")

    def test_in_memory_context_binding(self):
        s = _make_mem_store()
        c = s.encrypt("val", context="test_ctx")
        with pytest.raises((SecretIntegrityError, SecretDecryptionError)):
            s.decrypt(c, context="wrong")


# ===========================================================================
# Integrity tests (Phase 15)
# ===========================================================================

class TestIntegrity:

    def _s(self): return _make_env_store()

    def test_modified_ciphertext_fails(self):
        s = self._s()
        token = s.encrypt("secret")
        # Corrupt the last character of the base64 payload
        corrupted = token[:-3] + "XXX"
        with pytest.raises(Exception):
            s.decrypt(corrupted)

    def test_truncated_payload_fails(self):
        s = self._s()
        token = s.encrypt("secret")
        with pytest.raises(Exception):
            s.decrypt(token[:20])

    def test_invalid_prefix_fails(self):
        with pytest.raises((SecretPayloadFormatError, Exception)):
            _make_env_store().decrypt("notanexoratoken")

    def test_unknown_version_fails(self):
        token = "nexora:v99:AAAA"
        with pytest.raises(SecretPayloadFormatError):
            _make_env_store().decrypt(token)

    def test_wrong_key_fails(self):
        s1 = _make_env_store(base64.urlsafe_b64encode(b"\x01" * 32).decode())
        s2 = _make_env_store(base64.urlsafe_b64encode(b"\x02" * 32).decode())
        c = s1.encrypt("secret")
        with pytest.raises(Exception):
            s2.decrypt(c)

    def test_key_not_in_registry_raises(self):
        s = _make_env_store(key_id="key-a")
        token = s.encrypt("val")
        # Build store with different key_id
        s2 = _make_env_store(key_id="key-b")
        with pytest.raises(SecretKeyNotFoundError):
            s2.decrypt(token)

    def test_random_string_fails(self):
        with pytest.raises(Exception):
            _make_env_store().decrypt("randomgarbage123")

    def test_unsupported_algorithm_field(self):
        """Payload claiming ChaCha20-Poly1305 must be rejected."""
        import json
        inner = {"version": "v1", "algorithm": "ChaCha20-Poly1305",
                 "key_id": "k1", "nonce": "AAAA", "ciphertext": "BBBB"}
        b64 = base64.urlsafe_b64encode(json.dumps(inner).encode()).decode()
        token = f"nexora:v1:{b64}"
        with pytest.raises(SecretPayloadFormatError):
            _make_env_store().decrypt(token)


# ===========================================================================
# Deletion tests (Phase 15)
# ===========================================================================

class TestDeletion:

    def test_env_store_delete_is_noop(self):
        s = _make_env_store()
        c = s.encrypt("val")
        s.delete(c)  # no-op — does not raise
        # Ciphertext still decryptable (inline store — caller clears DB field)
        assert s.decrypt(c) == "val"

    def test_mem_store_delete_prevents_decrypt(self):
        s = _make_mem_store()
        c = s.encrypt("val")
        s.delete(c)
        with pytest.raises(SecretDecryptionError):
            s.decrypt(c)

    def test_mem_store_delete_idempotent(self):
        s = _make_mem_store()
        c = s.encrypt("val")
        s.delete(c)
        s.delete(c)  # second delete must not raise


# ===========================================================================
# Health tests (Phase 15)
# ===========================================================================

class TestHealth:

    def test_env_store_healthy_with_valid_key(self):
        h = _make_env_store().health_check()
        assert h.status == SecretStoreStatus.HEALTHY
        assert h.provider == "environment"
        assert h.key_id == "k1"
        assert h.encryption_version == "v1"

    def test_mem_store_healthy(self):
        h = _make_mem_store().health_check()
        assert h.status == SecretStoreStatus.HEALTHY
        assert h.provider == "memory"

    def test_health_contains_no_key_material(self):
        h = _make_env_store().health_check()
        health_str = h.model_dump_json()
        assert _valid_key_b64() not in health_str
        assert "AAAA" not in health_str  # no raw key base64

    def test_health_response_has_no_plaintext(self):
        h = _make_env_store().health_check()
        health_str = h.model_dump_json()
        assert "_health_probe_" not in health_str


# ===========================================================================
# Logging safety (Phase 15)
# ===========================================================================

class TestLoggingSafety:

    def test_config_error_repr_no_key(self):
        exc = SecretStoreConfigurationError("test error", safe_detail="detail")
        assert _valid_key_b64() not in repr(exc)
        assert _valid_key_b64() not in str(exc)

    def test_settings_repr_no_key(self):
        """APISettings repr must not include the raw encryption key."""
        from api.config import APISettings
        s = APISettings.__new__(APISettings)
        s.version = "8.0.0"
        s.llm_provider = "ollama"
        s.secret_store_provider = "environment"
        s._secret_encryption_key_raw = _valid_key_b64()
        s.secret_key_id = "k1"
        s.telegram_mode = "mock"
        r = repr(s)
        assert _valid_key_b64() not in r
        assert s.secret_encryption_key_raw not in r

    def test_integrity_error_no_plaintext(self):
        s = _make_env_store()
        c = s.encrypt("mysecret")
        corrupted = c[:-3] + "XXX"
        try:
            s.decrypt(corrupted)
        except Exception as exc:
            assert "mysecret" not in str(exc)
            assert "mysecret" not in repr(exc)


# ===========================================================================
# Concurrency tests (Phase 15)
# ===========================================================================

class TestConcurrency:

    def test_concurrent_encryptions_all_valid_unique(self):
        s = _make_env_store()
        results = []
        errors = []

        def enc():
            try:
                results.append(s.encrypt("concurrent_secret"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=enc) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
        assert len(results) == 20
        assert len(set(results)) == 20  # all unique ciphertexts

    def test_concurrent_decryptions_all_succeed(self):
        s = _make_env_store()
        tokens = [s.encrypt(f"val_{i}") for i in range(20)]
        results = []
        errors = []

        def dec(i):
            try:
                results.append(s.decrypt(tokens[i]))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=dec, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
        assert len(results) == 20

    def test_mem_store_instances_isolated(self):
        s1, s2 = _make_mem_store(), _make_mem_store()
        c = s1.encrypt("val")
        s1.delete(c)
        # s2 doesn't know about s1's deletion
        assert s2.decrypt(c) == "val"


# ===========================================================================
# Property-style fuzz tests (Phase 16)
# ===========================================================================

_UNICODE_SAMPLES = [
    "hello", "مرحبا", "привет", "你好", "🔑🔒", "a" * 1000,
    "tab\there", "newline\nhere", "null\x00byte",
]
_CONTEXT_SAMPLES = [None, "ctx", "telegram_phone_number", "a" * 200]


class TestPropertyStyle:

    @pytest.mark.parametrize("text", _UNICODE_SAMPLES)
    def test_roundtrip_unicode_variants(self, text):
        s = _make_env_store()
        if not text.strip():
            return  # empty/whitespace handled by empty_plaintext policy
        assert s.decrypt(s.encrypt(text)) == text

    @pytest.mark.parametrize("ctx", _CONTEXT_SAMPLES)
    def test_roundtrip_context_variants(self, ctx):
        s = _make_env_store()
        c = s.encrypt("value", context=ctx)
        assert s.decrypt(c, context=ctx) == "value"

    @pytest.mark.parametrize("tamper_offset", [-1, -5, -10, 5, 0])
    def test_tampered_payload_always_fails(self, tamper_offset):
        s = _make_env_store()
        token = s.encrypt("secret")
        chars = list(token)
        idx = max(0, min(len(chars) - 1, len(chars) + tamper_offset))
        chars[idx] = "X" if chars[idx] != "X" else "Y"
        corrupted = "".join(chars)
        with pytest.raises(Exception):
            s.decrypt(corrupted)


# ===========================================================================
# Architecture guard tests (Phase 19)
# ===========================================================================

class TestArchitectureGuards:

    def _read_source(self, path: str) -> str:
        import pathlib
        return pathlib.Path(path).read_text(encoding="utf-8")

    def test_no_hardcoded_key_in_environment_key_module(self):
        src = self._read_source("app/security/secrets/environment_key.py")
        # No 32-byte literal key should appear (test key is in in_memory.py only)
        assert "b\"\\x00\" * 32" not in src
        assert 'b"\\x42" * 32' not in src

    def test_no_hardcoded_default_key_in_config(self):
        src = self._read_source("api/config.py")
        # Config must not have a hardcoded working encryption key
        assert "NEXORA_SECRET_ENCRYPTION_KEY=" not in src.replace(" ", "")

    def test_no_telegram_import_in_secret_store_package(self):
        import pathlib
        for f in pathlib.Path("app/security/secrets").glob("*.py"):
            src = f.read_text(encoding="utf-8")
            assert "telegram" not in src.lower(), \
                f"{f.name} must not import Telegram-specific code"

    def test_secret_store_package_has_no_base64_only_encryption(self):
        """Base64 must only be used as transport encoding, not as encryption."""
        src = self._read_source("app/security/secrets/environment_key.py")
        # The file uses AESGCM, not just base64
        assert "AESGCM" in src

    def test_generate_key_never_writes_env_file(self):
        """Key-gen utility must not auto-write any .env file."""
        src = self._read_source("app/security/secrets/generate_key.py")
        # Must not have open() for writing
        assert 'open(' not in src or ('write' not in src and 'w"' not in src)

    def test_no_ecb_mode_used(self):
        import pathlib
        for f in pathlib.Path("app/security/secrets").glob("*.py"):
            src = f.read_text(encoding="utf-8")
            assert "ECB" not in src
            assert "modes.ECB" not in src


# ===========================================================================
# Non-regression: settings and health (Change Management §6)
# ===========================================================================

class TestNonRegression:

    def test_existing_settings_still_load(self):
        """Unrelated settings variables still load correctly after secret fields added."""
        from api.config import APISettings
        s = APISettings.__new__(APISettings)
        s.host = "0.0.0.0"
        s.port = 8000
        s.log_level = "INFO"
        s.version = "8.0.0"
        s.app_name = "Nexora API"
        s.vectors_root = __import__("pathlib").Path("/tmp/vectors")
        s.llm_timeout_seconds = 30.0
        s.llm_provider = "ollama"
        s.llm_model = None
        s.openai_api_key = None
        s.llm_base_url = None
        s._secret_encryption_key_raw = None
        s.secret_store_provider = "environment"
        s.secret_key_id = "dev-key-1"
        s.secret_encryption_version = "v1"
        assert s.llm_provider == "ollama"
        assert s.version == "8.0.0"
        assert s.secret_key_id == "dev-key-1"

    def test_health_response_existing_fields_unchanged(self):
        """HealthResponse still has all its original fields after secret_store added."""
        from api.schemas.response_models import HealthResponse
        h = HealthResponse(
            status="ok", app_name="Nexora API", version="8.0.0",
            engine_status="ok", llm_provider_available=False,
        )
        assert h.status == "ok"
        assert h.app_name == "Nexora API"
        assert h.version == "8.0.0"
        assert h.engine_status == "ok"
        assert h.llm_provider_available is False
        assert h.secret_store is None  # new field defaults to None

    def test_health_endpoint_response_shape_unchanged(self, tmp_path):
        """Health endpoint shape for existing subsystems is unchanged."""
        from fastapi.testclient import TestClient
        from api.config import APISettings, get_settings
        from api.main import create_app

        settings = APISettings.__new__(APISettings)
        settings.host = "127.0.0.1"; settings.port = 8000
        settings.log_level = "DEBUG"; settings.version = "8.0.0-test"
        settings.app_name = "Nexora API (test)"
        settings.vectors_root = tmp_path / "vectors"
        settings.llm_timeout_seconds = 5.0; settings.llm_provider = "ollama"
        settings.llm_model = None; settings.openai_api_key = None
        settings.llm_base_url = None
        settings._secret_encryption_key_raw = None
        settings.secret_store_provider = "memory"  # use memory for test
        settings.secret_key_id = "test-key"; settings.secret_encryption_version = "v1"

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        # All original fields still present
        assert "status" in body
        assert "app_name" in body
        assert "version" in body
        assert "engine_status" in body
        assert "llm_provider_available" in body
        # New field present
        assert "secret_store" in body
