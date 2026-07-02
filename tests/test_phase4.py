"""
tests/test_phase4.py — Comprehensive unit tests for Phase 4.

All tests use pytest's ``tmp_path`` fixture so ChromaDB writes to a
temporary directory that is cleaned up automatically.  No data is ever
written to the real data/vectors directory during testing.

Test coverage:
  - VectorStoreConfig creation and validation
  - StoragePersistence: directory creation, health check
  - CollectionManager: create, open, statistics, reset, schema validation
  - ChromaVectorStore: single insert, batch insert, duplicate ids, count,
    delete, update, get, reset, reopen persistence
  - Phase4Pipeline: integration tests with real ChromaDB (tmp_path)
  - Error handling: invalid inputs, uninitialised store, validation errors
"""

from __future__ import annotations

import math
import json
import pytest
from pathlib import Path
from typing import List

from models.embedded_document import EmbeddedDocument, utc_now_iso
from config.vector_config import VectorStoreConfig
from app.storage.vector_store.persistence import StoragePersistence
from app.storage.vector_store.collection_manager import CollectionManager
from app.storage.vector_store.chroma_store import ChromaVectorStore
from app.storage.vector_store.phase4_pipeline import Phase4Pipeline, StorageSummary
from exceptions.exceptions import (
    VectorStoreError,
    CollectionError,
    PersistenceError,
    StorageValidationError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAKE_DIM = 8


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _fake_vector(seed: int, dim: int = FAKE_DIM) -> tuple:
    """Return a deterministic L2-normalised vector."""
    raw = [((seed * 7 + i * 13) % 17 - 8) / 8.0 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return tuple(v / norm for v in raw)


def _make_embedded(
    doc_id: str = "doc-001",
    text: str = "Alice: Hello world",
    seed: int = 1,
    dim: int = FAKE_DIM,
    source_chat: str = "Alice & Bob",
    chunk_index: int = 0,
    token_count: int = 5,
) -> EmbeddedDocument:
    vec = _fake_vector(seed, dim)
    return EmbeddedDocument(
        document_id=doc_id,
        text=text,
        embedding=vec,
        metadata={
            "message_count": 2,
            "participant_count": 2,
            "contains_images": False,
            "contains_audio": False,
            "contains_video": False,
            "contains_documents": False,
            "attachment_count": 0,
            "conversation_duration_seconds": 300.0,
            "average_message_length": 12.5,
            "chunk_index": chunk_index,
            "token_count": token_count,
            "source_chat": source_chat,
            "embedding_model": "BAAI/bge-m3",
            "embedding_dim": dim,
            "participants": ["Alice", "Bob"],
            "attachments": [],
            "message_ids": [1, 2],
            "start_timestamp": "1/1/2024, 9:00 AM",
            "end_timestamp": "1/1/2024, 9:05 AM",
        },
        token_count=token_count,
        model_name="BAAI/bge-m3",
        embedding_dim=dim,
        created_at=utc_now_iso(),
    )


def _make_config(tmp_path: Path, collection: str = "test_col") -> VectorStoreConfig:
    return VectorStoreConfig(
        collection_name=collection,
        persist_directory=str(tmp_path),
        distance_metric="cosine",
        batch_size=10,
        embedding_model="BAAI/bge-m3",
        schema_version="1.0.0",
    )


def _make_store(tmp_path: Path, collection: str = "test_col") -> ChromaVectorStore:
    return ChromaVectorStore(_make_config(tmp_path, collection))


# ===========================================================================
# 1. VectorStoreConfig tests
# ===========================================================================

class TestVectorStoreConfig:

    def test_default_config_creates_successfully(self):
        config = VectorStoreConfig()
        assert config.collection_name
        assert config.persist_directory
        assert config.distance_metric in ("cosine", "l2", "ip")
        assert config.batch_size > 0
        assert config.embedding_model
        assert config.schema_version

    def test_custom_values_set_correctly(self, tmp_path):
        config = VectorStoreConfig(
            collection_name="my_col",
            persist_directory=str(tmp_path),
            distance_metric="l2",
            batch_size=50,
            embedding_model="custom-model",
            schema_version="2.0.0",
        )
        assert config.collection_name == "my_col"
        assert config.persist_directory == str(tmp_path)
        assert config.distance_metric == "l2"
        assert config.batch_size == 50
        assert config.embedding_model == "custom-model"
        assert config.schema_version == "2.0.0"

    def test_persist_path_is_pathlib_path(self, tmp_path):
        config = _make_config(tmp_path)
        assert isinstance(config.persist_path, Path)

    def test_empty_collection_name_raises(self, tmp_path):
        with pytest.raises(ValueError, match="collection_name"):
            VectorStoreConfig(collection_name="", persist_directory=str(tmp_path))

    def test_empty_persist_directory_raises(self):
        with pytest.raises(ValueError, match="persist_directory"):
            VectorStoreConfig(persist_directory="")

    def test_invalid_distance_metric_raises(self, tmp_path):
        with pytest.raises(ValueError, match="distance_metric"):
            VectorStoreConfig(
                persist_directory=str(tmp_path),
                distance_metric="euclidean",
            )

    def test_zero_batch_size_raises(self, tmp_path):
        with pytest.raises(ValueError, match="batch_size"):
            VectorStoreConfig(persist_directory=str(tmp_path), batch_size=0)

    def test_negative_batch_size_raises(self, tmp_path):
        with pytest.raises(ValueError, match="batch_size"):
            VectorStoreConfig(persist_directory=str(tmp_path), batch_size=-1)

    def test_empty_embedding_model_raises(self, tmp_path):
        with pytest.raises(ValueError, match="embedding_model"):
            VectorStoreConfig(persist_directory=str(tmp_path), embedding_model="")

    def test_empty_schema_version_raises(self, tmp_path):
        with pytest.raises(ValueError, match="schema_version"):
            VectorStoreConfig(persist_directory=str(tmp_path), schema_version="")

    def test_ip_distance_metric_valid(self, tmp_path):
        config = VectorStoreConfig(
            persist_directory=str(tmp_path), distance_metric="ip"
        )
        assert config.distance_metric == "ip"

    def test_repr_contains_collection_name(self, tmp_path):
        config = _make_config(tmp_path, collection="repr_test")
        assert "repr_test" in repr(config)


# ===========================================================================
# 2. StoragePersistence tests
# ===========================================================================

class TestStoragePersistence:

    def test_initialize_creates_directory(self, tmp_path):
        sub = tmp_path / "nested" / "chroma"
        config = _make_config(sub)
        persistence = StoragePersistence(config)
        persistence.initialize()
        assert sub.exists()
        persistence.close()

    def test_initialize_returns_client(self, tmp_path):
        import chromadb
        config = _make_config(tmp_path)
        persistence = StoragePersistence(config)
        client = persistence.initialize()
        assert client is not None
        persistence.close()

    def test_close_is_idempotent(self, tmp_path):
        config = _make_config(tmp_path)
        persistence = StoragePersistence(config)
        persistence.initialize()
        persistence.close()
        persistence.close()  # second close must not raise

    def test_client_is_none_after_close(self, tmp_path):
        config = _make_config(tmp_path)
        persistence = StoragePersistence(config)
        persistence.initialize()
        persistence.close()
        assert persistence.client is None

    def test_reinitialize_after_close_raises(self, tmp_path):
        config = _make_config(tmp_path)
        persistence = StoragePersistence(config)
        persistence.initialize()
        persistence.close()
        with pytest.raises(VectorStoreError):
            persistence.initialize()


# ===========================================================================
# 3. CollectionManager tests
# ===========================================================================

class TestCollectionManager:

    def _client(self, tmp_path):
        import chromadb
        return chromadb.PersistentClient(path=str(tmp_path))

    def test_get_or_create_creates_new_collection(self, tmp_path):
        client = self._client(tmp_path)
        config = _make_config(tmp_path, "mgr_test")
        mgr = CollectionManager(client=client, config=config)
        col = mgr.get_or_create()
        assert col is not None
        assert col.count() == 0

    def test_get_or_create_is_idempotent(self, tmp_path):
        client = self._client(tmp_path)
        config = _make_config(tmp_path, "idempotent_col")
        mgr = CollectionManager(client=client, config=config)
        col1 = mgr.get_or_create()
        col2 = mgr.get_or_create()
        assert col1.name == col2.name

    def test_statistics_returns_count(self, tmp_path):
        client = self._client(tmp_path)
        config = _make_config(tmp_path, "stats_col")
        mgr = CollectionManager(client=client, config=config)
        mgr.get_or_create()
        stats = mgr.statistics()
        assert "name" in stats
        assert "count" in stats
        assert stats["count"] == 0

    def test_statistics_before_get_or_create_raises(self, tmp_path):
        client = self._client(tmp_path)
        config = _make_config(tmp_path, "no_open_col")
        mgr = CollectionManager(client=client, config=config)
        with pytest.raises(CollectionError):
            mgr.statistics()

    def test_reset_clears_data(self, tmp_path):
        client = self._client(tmp_path)
        config = _make_config(tmp_path, "reset_col")
        mgr = CollectionManager(client=client, config=config)
        col = mgr.get_or_create()
        col.add(
            ids=["x"],
            embeddings=[list(_fake_vector(1))],
            documents=["text"],
            metadatas=[{"k": "v"}],
        )
        assert col.count() == 1
        new_col = mgr.reset()
        assert new_col.count() == 0

    def test_schema_mismatch_raises_collection_error(self, tmp_path):
        """Create a collection with model A, then try to open with model B."""
        import chromadb
        # First open with model A
        client1 = chromadb.PersistentClient(path=str(tmp_path))
        config_a = VectorStoreConfig(
            collection_name="schema_col",
            persist_directory=str(tmp_path),
            embedding_model="model-A",
        )
        mgr_a = CollectionManager(client=client1, config=config_a)
        mgr_a.get_or_create()

        # Re-open with model B — should raise CollectionError
        client2 = chromadb.PersistentClient(path=str(tmp_path))
        config_b = VectorStoreConfig(
            collection_name="schema_col",
            persist_directory=str(tmp_path),
            embedding_model="model-B",
        )
        mgr_b = CollectionManager(client=client2, config=config_b)
        with pytest.raises(CollectionError, match="embedding model"):
            mgr_b.get_or_create()


# ===========================================================================
# 4. ChromaVectorStore tests
# ===========================================================================

class TestChromaVectorStore:

    def _open_store(self, tmp_path, collection="store_test"):
        store = _make_store(tmp_path, collection)
        store.initialize()
        return store

    # ── Initialisation ───────────────────────────────────────────────

    def test_initialize_succeeds(self, tmp_path):
        store = _make_store(tmp_path)
        store.initialize()
        assert store.count() == 0
        store.close()

    def test_double_initialize_is_safe(self, tmp_path):
        store = _make_store(tmp_path)
        store.initialize()
        store.initialize()   # second call must not raise
        store.close()

    def test_operations_before_initialize_raise(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(VectorStoreError):
            store.count()

    # ── Single insert ─────────────────────────────────────────────────

    def test_single_insert(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("single-1")
        inserted = store.add_documents([doc])
        assert inserted == 1
        assert store.count() == 1
        store.close()

    def test_insert_returns_correct_count(self, tmp_path):
        store = self._open_store(tmp_path)
        docs = [_make_embedded(f"d{i}", seed=i) for i in range(5)]
        inserted = store.add_documents(docs)
        assert inserted == 5
        store.close()

    # ── Batch insert ──────────────────────────────────────────────────

    def test_batch_insert_all_stored(self, tmp_path):
        store = self._open_store(tmp_path, "batch_col")
        docs = [_make_embedded(f"batch-{i}", seed=i) for i in range(25)]
        store.add_documents(docs)
        assert store.count() == 25
        store.close()

    def test_batch_insert_respects_batch_size(self, tmp_path):
        """Insert 15 docs with batch_size=4 — all 15 must be stored."""
        config = VectorStoreConfig(
            collection_name="small_batch",
            persist_directory=str(tmp_path),
            batch_size=4,
        )
        store = ChromaVectorStore(config)
        store.initialize()
        docs = [_make_embedded(f"sb-{i}", seed=i) for i in range(15)]
        store.add_documents(docs)
        assert store.count() == 15
        store.close()

    # ── Duplicate ids ─────────────────────────────────────────────────

    def test_duplicate_ids_within_batch_raises(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("dup-id")
        with pytest.raises(StorageValidationError, match="Duplicate"):
            store.add_documents([doc, doc])
        store.close()

    def test_existing_id_skipped_on_second_add(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("existing-1")
        store.add_documents([doc])
        assert store.count() == 1
        # Second add of same ID returns 0 inserted
        inserted = store.add_documents([doc])
        assert inserted == 0
        assert store.count() == 1  # still only 1
        store.close()

    # ── Text preservation ─────────────────────────────────────────────

    def test_document_text_preserved(self, tmp_path):
        store = self._open_store(tmp_path)
        original_text = "Alice: This is an exact text string"
        doc = _make_embedded("text-check", text=original_text)
        store.add_documents([doc])
        result = store.get_document("text-check")
        assert result is not None
        assert result["text"] == original_text
        store.close()

    # ── Metadata preservation ─────────────────────────────────────────

    def test_metadata_source_chat_preserved(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("meta-1", source_chat="Alice & Bob")
        store.add_documents([doc])
        result = store.get_document("meta-1")
        assert result["metadata"]["source_chat"] == "Alice & Bob"
        store.close()

    def test_metadata_chunk_index_preserved(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("meta-2", chunk_index=7)
        store.add_documents([doc])
        result = store.get_document("meta-2")
        assert result["metadata"]["chunk_index"] == 7
        store.close()

    def test_metadata_token_count_preserved(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("meta-3", token_count=42)
        store.add_documents([doc])
        result = store.get_document("meta-3")
        assert result["metadata"]["token_count"] == 42
        store.close()

    def test_metadata_embedding_model_preserved(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("meta-4")
        store.add_documents([doc])
        result = store.get_document("meta-4")
        assert result["metadata"]["embedding_model"] == "BAAI/bge-m3"
        store.close()

    def test_metadata_schema_version_stored(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("meta-5")
        store.add_documents([doc])
        result = store.get_document("meta-5")
        assert result["metadata"]["schema_version"] == "1.0.0"
        store.close()

    def test_metadata_contains_images_flag(self, tmp_path):
        store = self._open_store(tmp_path)
        vec = _fake_vector(99)
        doc = EmbeddedDocument(
            document_id="img-flag",
            text="photo here",
            embedding=vec,
            metadata={
                "contains_images": True,
                "contains_audio": False,
                "contains_video": False,
                "contains_documents": False,
                "attachment_count": 1,
                "message_count": 1,
                "source_chat": "test",
                "chunk_index": 0,
                "token_count": 3,
                "participants": ["Alice"],
                "attachments": ["photo.jpg"],
                "message_ids": [1],
                "start_timestamp": "",
                "end_timestamp": "",
                "embedding_model": "BAAI/bge-m3",
                "embedding_dim": FAKE_DIM,
            },
            token_count=3,
            model_name="BAAI/bge-m3",
            embedding_dim=FAKE_DIM,
            created_at=utc_now_iso(),
        )
        store.add_documents([doc])
        result = store.get_document("img-flag")
        assert result["metadata"]["contains_images"] is True
        store.close()

    def test_metadata_created_at_stored(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("ts-check")
        store.add_documents([doc])
        result = store.get_document("ts-check")
        assert result["metadata"]["created_at"]
        store.close()

    # ── Embedding preservation ────────────────────────────────────────

    def test_embedding_round_trip(self, tmp_path):
        store = self._open_store(tmp_path)
        original_vec = _fake_vector(42)
        doc = _make_embedded("emb-rt", seed=42)
        store.add_documents([doc])
        result = store.get_document("emb-rt")
        assert result["embedding"] is not None
        assert len(result["embedding"]) == FAKE_DIM
        # All values should be approximately equal
        for orig, stored in zip(original_vec, result["embedding"]):
            assert abs(orig - stored) < 1e-5
        store.close()

    # ── count ─────────────────────────────────────────────────────────

    def test_count_increases_after_insert(self, tmp_path):
        store = self._open_store(tmp_path)
        assert store.count() == 0
        store.add_documents([_make_embedded("c1", seed=1)])
        assert store.count() == 1
        store.add_documents([_make_embedded("c2", seed=2)])
        assert store.count() == 2
        store.close()

    # ── delete ────────────────────────────────────────────────────────

    def test_delete_existing_document(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("del-1")
        store.add_documents([doc])
        assert store.count() == 1
        deleted = store.delete_document("del-1")
        assert deleted is True
        assert store.count() == 0
        store.close()

    def test_delete_nonexistent_returns_false(self, tmp_path):
        store = self._open_store(tmp_path)
        result = store.delete_document("ghost-id")
        assert result is False
        store.close()

    def test_get_returns_none_after_delete(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("del-get")
        store.add_documents([doc])
        store.delete_document("del-get")
        assert store.get_document("del-get") is None
        store.close()

    # ── update ────────────────────────────────────────────────────────

    def test_update_replaces_text(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("upd-1", text="original text")
        store.add_documents([doc])

        import dataclasses
        updated = dataclasses.replace(doc, text="updated text")
        store.update_document(updated)

        result = store.get_document("upd-1")
        assert result["text"] == "updated text"
        store.close()

    def test_update_nonexistent_raises(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("ghost-upd")
        with pytest.raises(StorageValidationError):
            store.update_document(doc)
        store.close()

    # ── get_document ─────────────────────────────────────────────────

    def test_get_nonexistent_returns_none(self, tmp_path):
        store = self._open_store(tmp_path)
        assert store.get_document("no-such-id") is None
        store.close()

    def test_get_returns_correct_id(self, tmp_path):
        store = self._open_store(tmp_path)
        doc = _make_embedded("get-id-check")
        store.add_documents([doc])
        result = store.get_document("get-id-check")
        assert result["id"] == "get-id-check"
        store.close()

    # ── reset ─────────────────────────────────────────────────────────

    def test_reset_removes_all_documents(self, tmp_path):
        store = self._open_store(tmp_path)
        docs = [_make_embedded(f"rst-{i}", seed=i) for i in range(5)]
        store.add_documents(docs)
        assert store.count() == 5
        store.reset()
        assert store.count() == 0
        store.close()

    def test_insert_after_reset_succeeds(self, tmp_path):
        store = self._open_store(tmp_path)
        store.add_documents([_make_embedded("pre-reset")])
        store.reset()
        store.add_documents([_make_embedded("post-reset")])
        assert store.count() == 1
        store.close()

    # ── Persistence (reopen) ──────────────────────────────────────────

    def test_data_persists_across_reopen(self, tmp_path):
        """Close the store and re-open it — data must survive."""
        config = _make_config(tmp_path, "persist_col")
        store1 = ChromaVectorStore(config)
        store1.initialize()
        docs = [_make_embedded(f"persist-{i}", seed=i) for i in range(3)]
        store1.add_documents(docs)
        count_before = store1.count()
        store1.close()

        store2 = ChromaVectorStore(config)
        store2.initialize()
        count_after = store2.count()
        store2.close()

        assert count_after == count_before

    def test_documents_retrievable_after_reopen(self, tmp_path):
        config = _make_config(tmp_path, "reopen_col")
        doc = _make_embedded("reopen-check", text="persistent text")

        store1 = ChromaVectorStore(config)
        store1.initialize()
        store1.add_documents([doc])
        store1.close()

        store2 = ChromaVectorStore(config)
        store2.initialize()
        result = store2.get_document("reopen-check")
        store2.close()

        assert result is not None
        assert result["text"] == "persistent text"

    # ── Validation ────────────────────────────────────────────────────

    def test_add_empty_list_raises(self, tmp_path):
        store = self._open_store(tmp_path)
        with pytest.raises(StorageValidationError):
            store.add_documents([])
        store.close()

    def test_add_non_embedded_document_raises(self, tmp_path):
        store = self._open_store(tmp_path)
        with pytest.raises(StorageValidationError):
            store.add_documents(["not a document"])  # type: ignore
        store.close()

    def test_delete_empty_id_raises(self, tmp_path):
        store = self._open_store(tmp_path)
        with pytest.raises(StorageValidationError):
            store.delete_document("")
        store.close()


# ===========================================================================
# 5. Phase4Pipeline integration tests
# ===========================================================================

class TestPhase4Pipeline:

    def _run(self, docs, tmp_path, collection="pipe_col") -> StorageSummary:
        config = _make_config(tmp_path, collection)
        return Phase4Pipeline(docs, config=config).run()

    def test_empty_input_returns_zero_summary(self, tmp_path):
        summary = self._run([], tmp_path)
        assert summary.documents_received == 0
        assert summary.documents_inserted == 0
        assert summary.final_count == 0

    def test_single_document_stored(self, tmp_path):
        docs = [_make_embedded("pipe-1")]
        summary = self._run(docs, tmp_path)
        assert summary.documents_received == 1
        assert summary.documents_inserted == 1
        assert summary.final_count == 1

    def test_multiple_documents_stored(self, tmp_path):
        docs = [_make_embedded(f"p{i}", seed=i) for i in range(10)]
        summary = self._run(docs, tmp_path)
        assert summary.documents_inserted == 10
        assert summary.final_count == 10

    def test_summary_collection_name_correct(self, tmp_path):
        docs = [_make_embedded("sum-col")]
        summary = self._run(docs, tmp_path, collection="named_col")
        assert summary.collection_name == "named_col"

    def test_summary_persist_directory_correct(self, tmp_path):
        docs = [_make_embedded("sum-dir")]
        config = _make_config(tmp_path)
        summary = Phase4Pipeline(docs, config=config).run()
        assert summary.persist_directory == str(tmp_path)

    def test_summary_elapsed_seconds_positive(self, tmp_path):
        docs = [_make_embedded("elapsed")]
        summary = self._run(docs, tmp_path)
        assert summary.elapsed_seconds >= 0.0

    def test_duplicate_documents_counted_as_skipped(self, tmp_path):
        docs = [_make_embedded(f"dup-{i}", seed=i) for i in range(3)]
        config = _make_config(tmp_path, "dup_col")
        # First run
        Phase4Pipeline(docs, config=config).run()
        # Second run with same docs
        summary = Phase4Pipeline(docs, config=config).run()
        assert summary.documents_skipped == 3
        assert summary.documents_inserted == 0
        assert summary.final_count == 3  # unchanged

    def test_partial_duplicates_correctly_counted(self, tmp_path):
        first_batch = [_make_embedded(f"a{i}", seed=i) for i in range(3)]
        config = _make_config(tmp_path, "partial_dup")
        Phase4Pipeline(first_batch, config=config).run()

        mixed = first_batch + [_make_embedded("new-1", seed=99)]
        summary = Phase4Pipeline(mixed, config=config).run()
        assert summary.documents_inserted == 1
        assert summary.documents_skipped == 3
        assert summary.final_count == 4

    def test_final_count_matches_db_after_pipeline(self, tmp_path):
        docs = [_make_embedded(f"fc-{i}", seed=i) for i in range(5)]
        config = _make_config(tmp_path, "fc_col")
        summary = Phase4Pipeline(docs, config=config).run()

        # Re-open and verify count independently
        store = ChromaVectorStore(config)
        store.initialize()
        db_count = store.count()
        store.close()

        assert summary.final_count == db_count == 5

    def test_invalid_documents_type_raises(self, tmp_path):
        with pytest.raises(TypeError):
            Phase4Pipeline("not a list")  # type: ignore

    def test_invalid_first_element_raises(self, tmp_path):
        with pytest.raises(TypeError):
            Phase4Pipeline(["not embedded"])  # type: ignore

    def test_str_summary_is_informative(self, tmp_path):
        docs = [_make_embedded("str-test")]
        summary = self._run(docs, tmp_path)
        s = str(summary)
        assert "inserted" in s
        assert "total_in_db" in s

    def test_metadata_retrievable_after_pipeline(self, tmp_path):
        """Insert via pipeline, retrieve directly and check metadata."""
        doc = _make_embedded("meta-pipe", source_chat="TestChat", chunk_index=3)
        config = _make_config(tmp_path, "meta_pipe_col")
        Phase4Pipeline([doc], config=config).run()

        store = ChromaVectorStore(config)
        store.initialize()
        result = store.get_document("meta-pipe")
        store.close()

        assert result is not None
        assert result["metadata"]["source_chat"] == "TestChat"
        assert result["metadata"]["chunk_index"] == 3
        assert result["metadata"]["embedding_model"] == "BAAI/bge-m3"


# ===========================================================================
# 6. Exception type tests
# ===========================================================================

class TestExceptionTypes:

    def test_vector_store_error_is_exception(self):
        err = VectorStoreError("vs error")
        assert isinstance(err, Exception)
        assert str(err) == "vs error"

    def test_collection_error_is_exception(self):
        err = CollectionError("col error")
        assert isinstance(err, Exception)

    def test_persistence_error_is_exception(self):
        err = PersistenceError("persist error")
        assert isinstance(err, Exception)

    def test_storage_validation_error_is_exception(self):
        err = StorageValidationError("val error")
        assert isinstance(err, Exception)
