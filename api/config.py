"""
api/config.py — API-layer settings for Phase 7.

Reads from environment variables (and an optional .env file via
python-dotenv if present).  Wraps — but does not replace — the existing
``config/`` dataclasses used by Phases 1-6.

All path values are expressed relative to the project root so that no
absolute filesystem paths appear in code or API responses.

Environment variables
---------------------
NEXORA_API_HOST             Host to bind (default: 0.0.0.0)
NEXORA_API_PORT             Port to bind (default: 8000)
NEXORA_API_LOG_LEVEL        Log level: DEBUG|INFO|WARNING|ERROR (default: INFO)
NEXORA_API_VERSION          API semantic version string (default: 7.0.0)
NEXORA_MAX_UPLOAD_BYTES     Maximum upload size in bytes (default: 209715200 = 200 MB)
NEXORA_UPLOAD_DIR           Directory for received ZIPs (default: data/raw/uploads)
NEXORA_EXTRACT_ROOT         Directory for ZIP extraction (default: data/extracted)
NEXORA_VECTORS_ROOT         Root directory for ChromaDB persistence (default: data/vectors)
NEXORA_LLM_TIMEOUT_SECONDS  Timeout for a single Phase 6 generation call (default: 30)
NEXORA_LLM_PROVIDER         Forwarded to LLMConfig (default: ollama)
NEXORA_LLM_MODEL            Forwarded to LLMConfig
OPENAI_API_KEY              Forwarded to LLMConfig
NEXORA_LLM_BASE_URL         Forwarded to LLMConfig
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root — all paths are relative to this
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    """Read an integer env var, falling back to *default*."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to *default*."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    """Read a string env var, falling back to *default*."""
    return os.environ.get(name, default)


def _env_path(name: str, default_relative: str) -> Path:
    """
    Read a path env var.  If the value is relative, it is resolved against
    the project root.  Returns an absolute ``Path``.
    """
    raw = os.environ.get(name)
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (_PROJECT_ROOT / p).resolve()
    return (_PROJECT_ROOT / default_relative).resolve()


class APISettings:
    """
    Immutable settings object for the Phase 7 API layer.

    Instantiated once at startup and shared via FastAPI dependency injection.
    Never constructed per-request.
    """

    def __init__(self) -> None:
        # Server
        self.host: str = _env_str("NEXORA_API_HOST", "0.0.0.0")
        self.port: int = _env_int("NEXORA_API_PORT", 8000)
        self.log_level: str = _env_str("NEXORA_API_LOG_LEVEL", "INFO").upper()
        self.version: str = _env_str("NEXORA_API_VERSION", "7.0.0")
        self.app_name: str = "Nexora API"

        # Upload limits and paths
        self.max_upload_bytes: int = _env_int(
            "NEXORA_MAX_UPLOAD_BYTES", 200 * 1024 * 1024  # 200 MB
        )
        self.upload_dir: Path = _env_path("NEXORA_UPLOAD_DIR", "data/raw/uploads")
        self.extract_root: Path = _env_path("NEXORA_EXTRACT_ROOT", "data/extracted")
        self.vectors_root: Path = _env_path("NEXORA_VECTORS_ROOT", "data/vectors")

        # LLM / Phase 6
        self.llm_timeout_seconds: float = _env_float("NEXORA_LLM_TIMEOUT_SECONDS", 30.0)
        self.llm_provider: str = _env_str("NEXORA_LLM_PROVIDER", "ollama")
        self.llm_model: str | None = os.environ.get("NEXORA_LLM_MODEL")
        self.openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
        self.llm_base_url: str | None = os.environ.get("NEXORA_LLM_BASE_URL")

    @property
    def project_root(self) -> Path:
        """Absolute path to the project root directory."""
        return _PROJECT_ROOT

    def __repr__(self) -> str:
        # Never include API keys
        return (
            f"APISettings(version={self.version!r}, "
            f"max_upload_bytes={self.max_upload_bytes}, "
            f"llm_provider={self.llm_provider!r})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton — imported by dependencies.py
# ---------------------------------------------------------------------------
_settings: APISettings | None = None


def get_settings() -> APISettings:
    """
    Return the shared ``APISettings`` singleton.

    Thread-safe for read-only use after the first call.
    Suitable as a FastAPI ``Depends`` target.
    """
    global _settings
    if _settings is None:
        _settings = APISettings()
    return _settings
