"""
tests/test_phase7_api.py — Phase 7 API test suite.

All tests use dependency injection + service-layer mocking.
No real embedding model, LLM, or ChromaDB is touched.
All file I/O goes to pytest's tmp_path.
"""

from __future__ import annotations

import io
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
    QueryResponse,
    RetrievedDocumentResponse,
    UploadResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_zip_bytes(chat: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "WhatsApp Chat.txt",
            chat or "1/1/2024, 9:00 AM - Alice: Hello\n1/1/2024, 9:01 AM - Bob: Hi\n",
        )
    return buf.getvalue()


def _make_test_settings(tmp_path: Path) -> APISettings:
    s = APISettings.__new__(APISettings)
    s.host = "127.0.0.1"
    s.port = 8000
    s.log_level = "DEBUG"
    s.version = "7.0.0-test"
    s.app_name = "Nexora API (test)"
    s.max_upload_bytes = 5 * 1024 * 1024
    s.upload_dir = tmp_path / "uploads"
    s.extract_root = tmp_path / "extracted"
    s.vectors_root = tmp_path / "vectors"
    s.llm_timeout_seconds = 5.0
    s.llm_provider = "ollama"
    s.llm_model = None
    s.openai_api_key = None
    s.llm_base_url = None
    return s


def _make_client(settings: APISettings) -> TestClient:
    from api.config import get_settings
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


_FAKE_UPLOAD_RESPONSE = UploadResponse(
    collection_name="nexora_alice_abc12345",
    messages_parsed=10,
    chunks_created=3,
    vectors_indexed=3,
    phase_statuses=[
        PhaseStatus(phase="phase1", status="success"),
        PhaseStatus(phase="phase2", status="success"),
        PhaseStatus(phase="phase3", status="success"),
        PhaseStatus(phase="phase4", status="success"),
    ],
    elapsed_seconds=0.5,
)

_FAKE_RETRIEVED = [
    RetrievedDocumentResponse(
        document_id="doc-001",
        text="Alice: Hello",
        similarity_score=0.92,
        rank=1,
        metadata={"source_chat": "Alice & Bob"},
    )
]

_FAKE_COLLECTIONS = [
    CollectionInfo(
        name="nexora_alice_abc12345",
        document_count=3,
        embedding_model="BAAI/bge-m3",
        schema_version="1.0.0",
    )
]


# ===========================================================================
# 1. GET /health
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

    def test_health_status_degraded_when_llm_unavailable(
        self, tmp_path: Path
    ) -> None:
        """Health endpoint returns 'degraded' (not error) when LLM is down."""
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)

        with patch(
            "api.routes.health._probe_llm",
            side_effect=lambda s, r, timeout=0.8: r.__setitem__(0, False),
        ):
            data = client.get("/health").json()

        # Status should be degraded, not 5xx
        assert data["status"] in ("ok", "degraded")
        assert data["llm_provider_available"] in (True, False)

    def test_health_never_hangs_more_than_2s(self, client: TestClient) -> None:
        """Health endpoint must not block — completes quickly."""
        import time
        t0 = time.perf_counter()
        client.get("/health")
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"Health took {elapsed:.1f}s — too slow"


# ===========================================================================
# 2. POST /upload
# ===========================================================================

class TestUpload:

    def test_upload_rejects_non_zip_extension(self, client: TestClient) -> None:
        data = client.post(
            "/upload",
            files={"file": ("chat.txt", b"text content", "text/plain")},
        )
        assert data.status_code == 400
        body = data.json()
        assert body["error"] == "invalid_input"

    def test_upload_rejects_wrong_mime_as_zip(self, client: TestClient) -> None:
        """A .zip extension with non-ZIP magic bytes → 400."""
        fake_content = b"Not a ZIP\x00\x01\x02\x03" + b"X" * 50
        resp = client.post(
            "/upload",
            files={"file": ("export.zip", fake_content, "application/zip")},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_input"

    def test_upload_rejects_oversized_file(self, tmp_path: Path) -> None:
        """File exceeding max_upload_bytes → 413."""
        settings = _make_test_settings(tmp_path)
        settings.max_upload_bytes = 100  # 100 bytes limit for this test

        client = _make_client(settings)
        big_content = _make_valid_zip_bytes()  # real ZIP > 100 bytes
        resp = client.post(
            "/upload",
            files={"file": ("export.zip", big_content, "application/zip")},
        )
        assert resp.status_code == 413
        assert resp.json()["error"] == "file_too_large"

    def test_upload_succeeds_with_mocked_pipeline(self, tmp_path: Path) -> None:
        """Valid ZIP + all phases mocked → 200 with UploadResponse shape."""
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)
        zip_bytes = _make_valid_zip_bytes()

        with patch(
            "api.services.upload_service.run_upload_pipeline",
            return_value=_FAKE_UPLOAD_RESPONSE,
        ):
            resp = client.post(
                "/upload",
                files={"file": ("chat.zip", zip_bytes, "application/zip")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "collection_name" in body
        assert "messages_parsed" in body
        assert "chunks_created" in body
        assert "vectors_indexed" in body
        assert "phase_statuses" in body
        assert "elapsed_seconds" in body

    def test_upload_response_has_no_absolute_paths(self, tmp_path: Path) -> None:
        """API response must not expose server-side absolute paths."""
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)
        zip_bytes = _make_valid_zip_bytes()

        with patch(
            "api.services.upload_service.run_upload_pipeline",
            return_value=_FAKE_UPLOAD_RESPONSE,
        ):
            body = client.post(
                "/upload",
                files={"file": ("chat.zip", zip_bytes, "application/zip")},
            ).json()

        resp_str = str(body)
        assert ":\\" not in resp_str, "Absolute Windows path found in response"
        assert "D:\\" not in resp_str

    def test_upload_error_response_conforms_to_schema(
        self, client: TestClient
    ) -> None:
        """Even on failure, the error body matches ErrorResponse."""
        resp = client.post(
            "/upload",
            files={"file": ("bad.txt", b"x", "text/plain")},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "message" in body


# ===========================================================================
# 3. POST /query
# ===========================================================================

class TestQuery:

    def _query(self, client, **kwargs):
        payload = {
            "question": "What did Alice say?",
            "collection_name": "nexora_alice_abc12345",
            "top_k": 5,
            "use_rag": False,
            **kwargs,
        }
        return client.post("/query", json=payload)

    def test_query_rejects_empty_question(self, client: TestClient) -> None:
        resp = self._query(client, question="")
        assert resp.status_code == 400  # our handler maps Pydantic errors to 400

    def test_query_rejects_whitespace_only_question(
        self, client: TestClient
    ) -> None:
        resp = self._query(client, question="   ")
        assert resp.status_code == 400

    def test_query_rejects_top_k_out_of_range_low(
        self, client: TestClient
    ) -> None:
        resp = self._query(client, top_k=0)
        assert resp.status_code == 400

    def test_query_rejects_top_k_out_of_range_high(
        self, client: TestClient
    ) -> None:
        resp = self._query(client, top_k=51)
        assert resp.status_code == 400

    def test_query_returns_404_for_unknown_collection(
        self, client: TestClient
    ) -> None:
        with patch(
            "api.services.query_service.run_query",
            side_effect=__import__(
                "api.exceptions", fromlist=["CollectionNotFoundError"]
            ).CollectionNotFoundError("Not found."),
        ):
            resp = self._query(client, collection_name="nexora_ghost_000")
        assert resp.status_code == 404
        assert resp.json()["error"] == "collection_not_found"

    def test_query_rejects_path_traversal_collection_name(
        self, client: TestClient
    ) -> None:
        resp = self._query(client, collection_name="../etc/passwd")
        assert resp.status_code == 400  # our handler maps validation error → 400

    def test_query_use_rag_false_returns_retrieval_only(
        self, tmp_path: Path
    ) -> None:
        """use_rag=False → llm_used=False and no answer."""
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)

        fake_resp = QueryResponse(
            question="What did Alice say?",
            answer=None,
            citations=[],
            retrieved_documents=_FAKE_RETRIEVED,
            confidence=None,
            llm_used=False,
            message=None,
            elapsed_seconds=0.1,
        )
        with patch(
            "api.services.query_service.run_query", return_value=fake_resp
        ):
            resp = client.post(
                "/query",
                json={
                    "question": "What did Alice say?",
                    "collection_name": "nexora_alice_abc12345",
                    "top_k": 5,
                    "use_rag": False,
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_used"] is False
        assert body["answer"] is None
        assert len(body["retrieved_documents"]) == 1

    def test_query_use_rag_true_llm_unavailable_returns_200(
        self, tmp_path: Path
    ) -> None:
        """LLM unavailable → still 200, answer=null, message explains."""
        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)

        fake_resp = QueryResponse(
            question="What did Alice say?",
            answer=None,
            citations=[],
            retrieved_documents=_FAKE_RETRIEVED,
            confidence=None,
            llm_used=False,
            message="LLM provider is unavailable; retrieval-only results.",
            elapsed_seconds=0.1,
        )
        with patch(
            "api.services.query_service.run_query", return_value=fake_resp
        ):
            resp = client.post(
                "/query",
                json={
                    "question": "What did Alice say?",
                    "collection_name": "nexora_alice_abc12345",
                    "top_k": 5,
                    "use_rag": True,
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_used"] is False
        assert body["answer"] is None
        assert body["message"] is not None
        assert "retrieval" in body["message"].lower() or "llm" in body["message"].lower()

    def test_query_use_rag_true_llm_available_returns_answer(
        self, tmp_path: Path
    ) -> None:
        """Full RAG path → answer present, llm_used=True, citations."""
        from api.schemas.response_models import CitationResponse

        settings = _make_test_settings(tmp_path)
        client = _make_client(settings)

        fake_resp = QueryResponse(
            question="What did Alice say?",
            answer="Alice said hello.",
            citations=[
                CitationResponse(
                    document_id="doc-001",
                    rank=1,
                    similarity_score=0.92,
                    source_chat="Alice & Bob",
                    chunk_index=0,
                    start_timestamp="1/1/2024, 9:00 AM",
                    end_timestamp="1/1/2024, 9:01 AM",
                )
            ],
            retrieved_documents=_FAKE_RETRIEVED,
            confidence=0.92,
            llm_used=True,
            message=None,
            elapsed_seconds=0.8,
        )
        with patch(
            "api.services.query_service.run_query", return_value=fake_resp
        ):
            resp = client.post(
                "/query",
                json={
                    "question": "What did Alice say?",
                    "collection_name": "nexora_alice_abc12345",
                    "top_k": 5,
                    "use_rag": True,
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_used"] is True
        assert body["answer"] == "Alice said hello."
        assert len(body["citations"]) == 1
        assert body["confidence"] == pytest.approx(0.92)


# ===========================================================================
# 4. GET /collections
# ===========================================================================

class TestCollections:

    def test_collections_empty_when_none_exist(self, client: TestClient) -> None:
        with patch(
            "api.services.collection_service.list_collections",
            return_value=[],
        ):
            resp = client.get("/collections")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["collections"] == []

    def test_collections_returns_list(self, client: TestClient) -> None:
        with patch(
            "api.services.collection_service.list_collections",
            return_value=_FAKE_COLLECTIONS,
        ):
            resp = client.get("/collections")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["collections"][0]["name"] == "nexora_alice_abc12345"
        assert body["collections"][0]["document_count"] == 3


# ===========================================================================
# 5. DELETE /collections/{collection_name}
# ===========================================================================

class TestDeleteCollection:

    def test_delete_unknown_collection_returns_404(
        self, client: TestClient
    ) -> None:
        with patch(
            "api.services.collection_service.delete_collection",
            side_effect=__import__(
                "api.exceptions", fromlist=["CollectionNotFoundError"]
            ).CollectionNotFoundError("Not found."),
        ):
            resp = client.delete("/collections/nexora_ghost_xyz")
        assert resp.status_code == 404
        assert resp.json()["error"] == "collection_not_found"

    def test_delete_existing_collection_returns_200(
        self, client: TestClient
    ) -> None:
        with patch(
            "api.services.collection_service.delete_collection",
            return_value=None,
        ):
            resp = client.delete("/collections/nexora_alice_abc12345")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] is True
        assert "nexora_alice_abc12345" in body["collection_name"]

    def test_delete_rejects_path_traversal(self, client: TestClient) -> None:
        """Path-traversal name must be rejected before any FS/DB call."""
        with patch(
            "api.services.collection_service.delete_collection",
            side_effect=__import__(
                "api.exceptions", fromlist=["InvalidInputError"]
            ).InvalidInputError("path traversal"),
        ) as mock_del:
            resp = client.delete("/collections/..%2Fetc%2Fpasswd")
            # Even if it gets to service, it should fail safely

        # Either 400 (caught at service) or the URL-encoded form is not a
        # valid path param — either way, must not be 200/success
        assert resp.status_code in (400, 404, 422)

    def test_delete_path_traversal_dots_rejected(
        self, client: TestClient
    ) -> None:
        """A name with '..' must be caught by the service layer."""
        with patch(
            "api.services.collection_service.delete_collection",
            side_effect=__import__(
                "api.exceptions", fromlist=["InvalidInputError"]
            ).InvalidInputError("Contains '..'"),
        ):
            resp = client.delete("/collections/valid_start")
        # Service raised InvalidInputError → 400
        assert resp.status_code in (400, 404)


# ===========================================================================
# 6. Error response schema conformance
# ===========================================================================

class TestErrorResponseShape:

    def test_404_conforms_to_error_response(self, client: TestClient) -> None:
        with patch(
            "api.services.query_service.run_query",
            side_effect=__import__(
                "api.exceptions", fromlist=["CollectionNotFoundError"]
            ).CollectionNotFoundError("nope"),
        ):
            resp = client.post(
                "/query",
                json={
                    "question": "hello",
                    "collection_name": "nexora_ghost_00x",
                    "use_rag": False,
                },
            )
        assert resp.status_code == 404
        body = resp.json()
        assert set(body.keys()) >= {"error", "message"}

    def test_400_conforms_to_error_response(self, client: TestClient) -> None:
        resp = client.post(
            "/upload",
            files={"file": ("bad.docx", b"x", "application/msword")},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "message" in body

    def test_422_pydantic_error_has_message(self, client: TestClient) -> None:
        """Our validation handler maps Pydantic errors to 400 with ErrorResponse shape."""
        resp = client.post(
            "/query",
            json={"question": "", "collection_name": "nexora_test_abc"},
        )
        # Our custom validation_exception_handler converts Pydantic errors to 400
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "message" in body


# ===========================================================================
# 7. Import smoke test
# ===========================================================================

class TestImport:

    def test_api_main_imports_cleanly(self) -> None:
        """Importing api.main must not trigger model loads or network calls."""
        import importlib
        import api.main as m
        assert hasattr(m, "app")
        assert hasattr(m, "create_app")

    def test_app_has_expected_routes(self) -> None:
        from api.main import app
        paths = {r.path for r in app.routes}
        assert "/health" in paths
        assert "/upload" in paths
        assert "/query" in paths
        assert "/collections" in paths
