"""
tests/test_phase7_api.py — Nexora API test suite.

Nexora is a Telegram AI Knowledge Retrieval Platform.
All tests use dependency injection + service-layer mocking.
No real embedding model, LLM, or ChromaDB is touched.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.config import APISettings
from api.main import create_app
from api.schemas.response_models import (
    CollectionInfo,
    QueryResponse,
    RetrievedDocumentResponse,
)


def _make_test_settings(tmp_path: Path) -> APISettings:
    s = APISettings.__new__(APISettings)
    s.host = "127.0.0.1"
    s.port = 8000
    s.log_level = "DEBUG"
    s.version = "8.0.0-test"
    s.app_name = "Nexora API (test)"
    s.vectors_root = tmp_path / "vectors"
    s.llm_timeout_seconds = 5.0
    s.llm_provider = "ollama"
    s.llm_model = None
    s.openai_api_key = None
    s.llm_base_url = None
    s.secret_store_provider = "memory"
    s._secret_encryption_key_raw = None
    s.secret_key_id = "test-key"
    s.secret_encryption_version = "v1"
    return s


def _make_client(settings: APISettings) -> TestClient:
    from api.config import get_settings
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


_FAKE_RETRIEVED = [
    RetrievedDocumentResponse(
        document_id="doc-001",
        text="Alice: Hello",
        similarity_score=0.92,
        rank=1,
        metadata={"source": "telegram", "conversation_id": "chat1"},
    )
]

_FAKE_COLLECTIONS = [
    CollectionInfo(
        name="nexora_test_col1",
        document_count=3,
        embedding_model="BAAI/bge-m3",
        schema_version="1.0.0",
    )
]


# ===========================================================================
# GET /health
# ===========================================================================

class TestHealth:

    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_shape(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "status" in data
        assert "app_name" in data
        assert "version" in data
        assert "engine_status" in data
        assert "llm_provider_available" in data

    def test_health_never_hangs(self, client: TestClient) -> None:
        import time
        t0 = time.perf_counter()
        client.get("/health")
        assert time.perf_counter() - t0 < 5.0

    def test_no_upload_route(self, client: TestClient) -> None:
        """POST /upload must not exist in the Telegram-only architecture."""
        resp = client.post("/upload", files={"file": ("x.zip", b"PK\x03\x04", "application/zip")})
        assert resp.status_code == 404


# ===========================================================================
# POST /query
# ===========================================================================

class TestQuery:

    def _query(self, client, **kwargs):
        payload = {
            "question": "What did Alice say?",
            "collection_name": "nexora_test_col1",
            "top_k": 5,
            "use_rag": False,
            **kwargs,
        }
        return client.post("/query", json=payload)

    def test_query_rejects_empty_question(self, client: TestClient) -> None:
        assert self._query(client, question="").status_code == 400

    def test_query_rejects_whitespace_only_question(self, client: TestClient) -> None:
        assert self._query(client, question="   ").status_code == 400

    def test_query_rejects_top_k_out_of_range_low(self, client: TestClient) -> None:
        assert self._query(client, top_k=0).status_code == 400

    def test_query_rejects_top_k_out_of_range_high(self, client: TestClient) -> None:
        assert self._query(client, top_k=51).status_code == 400

    def test_query_returns_404_for_unknown_collection(self, client: TestClient) -> None:
        with patch(
            "api.services.query_service.run_query",
            side_effect=__import__(
                "api.exceptions", fromlist=["CollectionNotFoundError"]
            ).CollectionNotFoundError("Not found."),
        ):
            resp = self._query(client, collection_name="nexora_ghost_000")
        assert resp.status_code == 404

    def test_query_rejects_path_traversal_collection_name(self, client: TestClient) -> None:
        assert self._query(client, collection_name="../etc/passwd").status_code == 400

    def test_query_use_rag_false_returns_retrieval_only(self, tmp_path: Path) -> None:
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)
        fake_resp = QueryResponse(
            question="What did Alice say?",
            answer=None, citations=[], retrieved_documents=_FAKE_RETRIEVED,
            confidence=None, llm_used=False, message=None, elapsed_seconds=0.1,
        )
        with patch("api.services.query_service.run_query", return_value=fake_resp):
            resp = client.post("/query", json={
                "question": "What did Alice say?",
                "collection_name": "nexora_test_col1",
                "top_k": 5, "use_rag": False,
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_used"] is False
        assert body["answer"] is None
        assert len(body["retrieved_documents"]) == 1

    def test_query_llm_unavailable_returns_200(self, tmp_path: Path) -> None:
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)
        fake_resp = QueryResponse(
            question="What did Alice say?",
            answer=None, citations=[], retrieved_documents=_FAKE_RETRIEVED,
            confidence=None, llm_used=False,
            message="LLM provider is unavailable; retrieval-only results.",
            elapsed_seconds=0.1,
        )
        with patch("api.services.query_service.run_query", return_value=fake_resp):
            resp = client.post("/query", json={
                "question": "What did Alice say?",
                "collection_name": "nexora_test_col1",
                "top_k": 5, "use_rag": True,
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_used"] is False
        assert body["answer"] is None

    def test_query_rag_returns_answer(self, tmp_path: Path) -> None:
        from api.schemas.response_models import CitationResponse
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)
        fake_resp = QueryResponse(
            question="What did Alice say?",
            answer="Alice said hello.",
            citations=[CitationResponse(
                document_id="doc-001", rank=1, similarity_score=0.92,
                source_chat="chat1", chunk_index=0,
                start_timestamp="2026-07-14T10:00:00Z",
                end_timestamp="2026-07-14T10:01:00Z",
            )],
            retrieved_documents=_FAKE_RETRIEVED,
            confidence=0.92, llm_used=True, message=None, elapsed_seconds=0.8,
        )
        with patch("api.services.query_service.run_query", return_value=fake_resp):
            resp = client.post("/query", json={
                "question": "What did Alice say?",
                "collection_name": "nexora_test_col1",
                "top_k": 5, "use_rag": True,
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_used"] is True
        assert body["answer"] == "Alice said hello."


# ===========================================================================
# GET /collections
# ===========================================================================

class TestCollections:

    def test_collections_empty(self, client: TestClient) -> None:
        with patch("api.services.collection_service.list_collections", return_value=[]):
            resp = client.get("/collections")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_collections_returns_list(self, client: TestClient) -> None:
        with patch("api.services.collection_service.list_collections",
                   return_value=_FAKE_COLLECTIONS):
            resp = client.get("/collections")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


# ===========================================================================
# DELETE /collections/{name}
# ===========================================================================

class TestDeleteCollection:

    def test_delete_unknown_returns_404(self, client: TestClient) -> None:
        with patch(
            "api.services.collection_service.delete_collection",
            side_effect=__import__(
                "api.exceptions", fromlist=["CollectionNotFoundError"]
            ).CollectionNotFoundError("nope"),
        ):
            resp = client.delete("/collections/nexora_ghost_xyz")
        assert resp.status_code == 404

    def test_delete_existing_returns_200(self, client: TestClient) -> None:
        with patch("api.services.collection_service.delete_collection", return_value=None):
            resp = client.delete("/collections/nexora_test_col1")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ===========================================================================
# Error schema
# ===========================================================================

class TestErrorResponseShape:

    def test_400_conforms_to_schema(self, client: TestClient) -> None:
        resp = client.post("/query", json={"question": "", "collection_name": "nexora_test"})
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "message" in body


# ===========================================================================
# Architecture guard
# ===========================================================================

class TestArchitectureGuard:
    """Active WhatsApp runtime references must be zero."""

    def test_no_whatsapp_import_in_api_main(self) -> None:
        import ast, pathlib
        source = pathlib.Path("api/main.py").read_text(encoding="utf-8")
        assert "whatsapp" not in source.lower(), \
            "api/main.py must not reference whatsapp"

    def test_no_whatsapp_import_in_query_service(self) -> None:
        import pathlib
        source = pathlib.Path("api/services/query_service.py").read_text(encoding="utf-8")
        assert "whatsapp" not in source.lower()

    def test_upload_route_does_not_exist(self) -> None:
        """POST /upload (WhatsApp ZIP import) must not be registered."""
        from api.main import app
        paths = {r.path for r in app.routes}
        assert "/upload" not in paths, \
            "/upload endpoint must not exist in the Telegram-only architecture"

    def test_telegram_routes_exist(self) -> None:
        from api.main import app
        paths = {r.path for r in app.routes}
        assert "/integrations/telegram/status" in paths
        assert "/integrations/telegram/chats" in paths

    def test_app_imports_cleanly(self) -> None:
        import api.main as m
        assert hasattr(m, "app")
        assert hasattr(m, "create_app")
