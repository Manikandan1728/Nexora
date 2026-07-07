"""
tests/conftest.py — Shared pytest fixtures for Phase 7 API tests.

All heavy dependencies (embedding model, LLM providers, ChromaDB) are
replaced with lightweight fakes via ``app.dependency_overrides`` and
service-layer mocks.  No real network calls, no real model loads, no
disk writes outside ``tmp_path``.
"""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.config import APISettings
from api.main import create_app
from api.schemas.response_models import (
    CollectionInfo,
    PhaseStatus,
    UploadResponse,
)


# ---------------------------------------------------------------------------
# Minimal valid ZIP fixture (WhatsApp-like content)
# ---------------------------------------------------------------------------

def _make_valid_zip(tmp_path: Path, chat_text: str | None = None) -> Path:
    """Create a minimal valid WhatsApp ZIP in *tmp_path*."""
    text = chat_text or (
        "1/1/2024, 9:00 AM - Alice: Hello\n"
        "1/1/2024, 9:01 AM - Bob: Hi\n"
    )
    zip_path = tmp_path / "test_chat.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("WhatsApp Chat.txt", text)
    return zip_path


@pytest.fixture(scope="session")
def valid_zip_bytes() -> bytes:
    """In-memory bytes of a minimal valid WhatsApp ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "WhatsApp Chat.txt",
            "1/1/2024, 9:00 AM - Alice: Hello\n1/1/2024, 9:01 AM - Bob: Hi\n",
        )
    return buf.getvalue()


@pytest.fixture(scope="session")
def non_zip_bytes() -> bytes:
    """Bytes that look like a .zip extension but fail magic-byte check."""
    return b"This is definitely not a ZIP file content at all."


@pytest.fixture(scope="session")
def truncated_zip_magic_bytes() -> bytes:
    """4 bytes that pass extension check but fail magic byte PK\\x03\\x04."""
    return b"\xFF\xFE\xFD\xFC" + b"X" * 100


# ---------------------------------------------------------------------------
# Fake APISettings pointing to tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_settings(tmp_path: Path) -> APISettings:
    """
    APISettings with all paths redirected to *tmp_path*.

    No real data/vectors, data/raw, or data/extracted directories are used.
    """
    settings = APISettings.__new__(APISettings)
    settings.host = "127.0.0.1"
    settings.port = 8000
    settings.log_level = "DEBUG"
    settings.version = "7.0.0-test"
    settings.app_name = "Nexora API (test)"
    settings.max_upload_bytes = 10 * 1024 * 1024  # 10 MB for tests
    settings.upload_dir = tmp_path / "uploads"
    settings.extract_root = tmp_path / "extracted"
    settings.vectors_root = tmp_path / "vectors"
    settings.llm_timeout_seconds = 5.0
    settings.llm_provider = "ollama"
    settings.llm_model = None
    settings.openai_api_key = None
    settings.llm_base_url = None
    return settings


# ---------------------------------------------------------------------------
# Mock upload service result
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_upload_response() -> UploadResponse:
    """A deterministic fake UploadResponse for upload tests."""
    return UploadResponse(
        collection_name="nexora_test_abc12345",
        messages_parsed=10,
        chunks_created=3,
        vectors_indexed=3,
        phase_statuses=[
            PhaseStatus(phase="phase1", status="success"),
            PhaseStatus(phase="phase2", status="success"),
            PhaseStatus(phase="phase3", status="success"),
            PhaseStatus(phase="phase4", status="success"),
        ],
        elapsed_seconds=1.23,
    )


# ---------------------------------------------------------------------------
# Mock collection list
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_collections() -> list:
    """Two fake CollectionInfo objects for collection list tests."""
    return [
        CollectionInfo(
            name="nexora_test_col1",
            document_count=42,
            embedding_model="BAAI/bge-m3",
            schema_version="1.0.0",
        ),
        CollectionInfo(
            name="nexora_test_col2",
            document_count=7,
            embedding_model="BAAI/bge-m3",
            schema_version="1.0.0",
        ),
    ]


# ---------------------------------------------------------------------------
# TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(test_settings: APISettings) -> Generator[TestClient, None, None]:
    """
    TestClient with all heavy dependencies overridden.

    Uses ``app.dependency_overrides`` so routes get fake settings without
    hitting real env vars, real ChromaDB, or real models.
    """
    from api.config import get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
