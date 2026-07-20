"""
api/config.py — API-layer settings for Nexora.

Nexora is a Telegram AI Knowledge Retrieval Platform powered by RAG.

Environment variables
---------------------
NEXORA_API_HOST             Host to bind (default: 0.0.0.0)
NEXORA_API_PORT             Port to bind (default: 8000)
NEXORA_API_LOG_LEVEL        Log level: DEBUG|INFO|WARNING|ERROR (default: INFO)
NEXORA_API_VERSION          API semantic version string (default: 8.0.0)
NEXORA_VECTORS_ROOT         Root directory for ChromaDB persistence (default: data/vectors)
NEXORA_LLM_TIMEOUT_SECONDS  Timeout for a single RAG generation call (default: 30)
NEXORA_LLM_PROVIDER         Forwarded to LLMConfig (default: ollama)
NEXORA_LLM_MODEL            Forwarded to LLMConfig
OPENAI_API_KEY              Forwarded to LLMConfig
NEXORA_LLM_BASE_URL         Forwarded to LLMConfig

Secret store (Part 2A — generic, not yet wired to Telegram persistence):
NEXORA_SECRET_STORE_PROVIDER   "environment" or "memory" (default: environment)
NEXORA_SECRET_ENCRYPTION_KEY   Base64url-encoded 32-byte AES-256 key (required if provider=environment)
NEXORA_SECRET_KEY_ID           Key identifier for payload rotation (default: dev-key-1)
NEXORA_SECRET_ENCRYPTION_VERSION  Payload version tag (default: v1)
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_path(name: str, default_relative: str) -> Path:
    raw = os.environ.get(name)
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (_PROJECT_ROOT / p).resolve()
    return (_PROJECT_ROOT / default_relative).resolve()


class APISettings:
    """
    Immutable settings for the Nexora API layer.
    Instantiated once at startup; shared via FastAPI dependency injection.
    """

    def __init__(self) -> None:
        # Server
        self.host: str = _env_str("NEXORA_API_HOST", "0.0.0.0")
        self.port: int = _env_int("NEXORA_API_PORT", 8000)
        self.log_level: str = _env_str("NEXORA_API_LOG_LEVEL", "INFO").upper()
        self.version: str = _env_str("NEXORA_API_VERSION", "8.0.0")
        self.app_name: str = "Nexora API"

        # Storage
        self.vectors_root: Path = _env_path("NEXORA_VECTORS_ROOT", "data/vectors")

        # LLM / RAG generation
        self.llm_timeout_seconds: float = _env_float("NEXORA_LLM_TIMEOUT_SECONDS", 30.0)
        self.llm_provider: str = _env_str("NEXORA_LLM_PROVIDER", "ollama")
        self.llm_model: str | None = os.environ.get("NEXORA_LLM_MODEL")
        self.openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
        self.llm_base_url: str | None = os.environ.get("NEXORA_LLM_BASE_URL")

        # Secret store (Part 2A — DR-S2 fail-fast if provider=environment and key missing)
        self.secret_store_provider: str = _env_str(
            "NEXORA_SECRET_STORE_PROVIDER", "environment"
        )
        # Key is stored as raw string; never printed or repr'd.
        self._secret_encryption_key_raw: str | None = os.environ.get(
            "NEXORA_SECRET_ENCRYPTION_KEY"
        )
        self.secret_key_id: str = _env_str("NEXORA_SECRET_KEY_ID", "dev-key-1")
        self.secret_encryption_version: str = _env_str(
            "NEXORA_SECRET_ENCRYPTION_VERSION", "v1"
        )

        # Telegram Authentication (Part 2C)
        self.telegram_mode: str = _env_str("TELEGRAM_MODE", "mock").lower()
        self.telegram_api_id: int | None = _env_int("TELEGRAM_API_ID", 0) or None
        self._telegram_api_hash: str | None = os.environ.get("TELEGRAM_API_HASH")
        self.telegram_device_model: str = _env_str("TELEGRAM_DEVICE_MODEL", "Nexora")
        self.telegram_system_version: str | None = os.environ.get("TELEGRAM_SYSTEM_VERSION")
        self.telegram_app_version: str | None = os.environ.get("TELEGRAM_APP_VERSION")
        self.telegram_lang_code: str = _env_str("TELEGRAM_LANG_CODE", "en")
        self.telegram_system_lang_code: str = _env_str("TELEGRAM_SYSTEM_LANG_CODE", "en")

        if self.telegram_mode == "real" and (not self.telegram_api_id or not self._telegram_api_hash):
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required when TELEGRAM_MODE=real")

    @property
    def secret_encryption_key_raw(self) -> str | None:
        """Raw base64url key string. Never log or repr this value."""
        return self._secret_encryption_key_raw

    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT

    @property
    def telegram_api_hash(self) -> str | None:
        """Raw API hash. Never log or repr this value."""
        return self._telegram_api_hash

    def __repr__(self) -> str:
        # SECURITY: never include secret_encryption_key_raw or telegram_api_hash in repr
        return (
            f"APISettings(version={self.version!r}, "
            f"llm_provider={self.llm_provider!r}, "
            f"secret_store_provider={self.secret_store_provider!r}, "
            f"secret_key_id={self.secret_key_id!r}, "
            f"telegram_mode={self.telegram_mode!r})"
        )


_settings: APISettings | None = None


def get_settings() -> APISettings:
    """Return the shared APISettings singleton. Suitable as FastAPI Depends target."""
    global _settings
    if _settings is None:
        _settings = APISettings()
    return _settings
