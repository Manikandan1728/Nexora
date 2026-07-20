"""
tests/conftest.py — Shared pytest fixtures for Nexora API tests.

Nexora is a Telegram AI Knowledge Retrieval Platform.
All heavy dependencies are replaced with lightweight fakes.
No real network calls, no real model loads, no disk writes outside tmp_path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from api.config import APISettings
from api.main import create_app
from api.schemas.response_models import CollectionInfo


# ---------------------------------------------------------------------------
# Fake APISettings pointing to tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_settings(tmp_path: Path) -> APISettings:
    """APISettings with all paths redirected to tmp_path."""
    settings = APISettings.__new__(APISettings)
    settings.host = "127.0.0.1"
    settings.port = 8000
    settings.log_level = "DEBUG"
    settings.version = "8.0.0-test"
    settings.app_name = "Nexora API (test)"
    settings.vectors_root = tmp_path / "vectors"
    settings.llm_timeout_seconds = 5.0
    settings.llm_provider = "ollama"
    settings.llm_model = None
    settings.openai_api_key = None
    settings.llm_base_url = None
    # Secret store defaults for tests
    settings.secret_store_provider = "memory"
    settings._secret_encryption_key_raw = None
    settings.secret_key_id = "test-key"
    settings.secret_encryption_version = "v1"
    settings.telegram_mode = "mock"
    settings.telegram_api_id = None
    settings._telegram_api_hash = None
    return settings


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
    """TestClient with all heavy dependencies overridden."""
    from api.config import get_settings
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

# ---------------------------------------------------------------------------
# Mock Embedding Model
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_embedding_model(monkeypatch):
    """
    Prevent loading the real BGE-M3 model during tests.
    Any call to embed_batch will return dummy embeddings.
    """
    def mock_embed_batch(self, texts):
        return [[0.0] * 8 for _ in texts]

    from app.vectorization.embedding_model import EmbeddingModel
    monkeypatch.setattr(EmbeddingModel, "embed_batch", mock_embed_batch)
    # Also mock embed_text just in case
    monkeypatch.setattr(EmbeddingModel, "embed_text", lambda self, text: [0.0] * 8)
