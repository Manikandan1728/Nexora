"""
tests/test_phase5.py — Comprehensive unit tests for Phase 5.

All ChromaDB tests use pytest's tmp_path fixture so no data is written
to the real data/vectors directory.

All query embedding tests use a FakeQueryEmbedder that returns
deterministic vectors without loading BGE-M3 model weights.

Coverage:
  - RetrievedDocument model validation
  - RetrievalConfig validation
  - QueryPreprocessor: empty, whitespace, unicode, newlines, type check
  - QueryEmbedder: success, failure, empty query guard
  - MetadataFilter: equality, operators, unknown fields, bad types, multi
  - SimilaritySearch: results, empty collection, threshold, distance conversion
  - RetrievalPipeline: integration with real ChromaDB (tmp_path)
  - Exception types
"""

from __future__ import annotations

import math
import pytest
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock

import chromadb

from models.retrieved_document import RetrievedDocument
from config.retrieval_config import RetrievalConfig
from app.retrieval.query_preprocessor import QueryPreprocessor
from app.retrieval.query_embedder import IQueryEmbedder, QueryEmbedder
from app.retrieval.metadata_filter import MetadataFilter
from app.retrieval.similarity_search import SimilaritySearch
from app.retrieval.retrieval_pipeline import RetrievalPipeline

from exceptions.exceptions import (
    QueryValidationError,
    QueryEmbeddingError,
    SimilaritySearchError,
    MetadataFilterError,
    RetrievalError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAKE_DIM = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_vector(seed: int, dim: int = FAKE_DIM) -> List[float]:
    raw = [((seed * 7 + i * 13) % 17 - 8) / 8.0 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


class FakeQueryEmbedder(IQueryEmbedder):
    """Test double — returns deterministic fake vectors without loading weights."""

    def __init__(self, dim: int = FAKE_DIM, should_fail: bool = False):
        self._dim = dim
        self._should_fail = should_fail
        self.embed_calls = 0

    def embed(self, query: str) -> List[float]:
        if self._should_fail:
            raise QueryEmbeddingError("FakeQueryEmbedder forced failure.")
        if not query or not query.strip():
            raise QueryEmbeddingError("Empty query.")
        self.embed_calls += 1
        seed = sum(ord(c) for c in query) % 100
        return _fake_vector(seed, self._dim)

    @property
    def embedding_dim(self) -> int:
        return self._dim


def _make_retrieval_config(tmp_path: Path, collection: str = "test_ret") -> RetrievalConfig:
    return RetrievalConfig(
        collection_name=collection,
        persist_directory=str(tmp_path),
        embedding_model="BAAI/bge-m3",
        top_k=5,
        score_threshold=0.0,
        distance_metric="cosine",
    )


def _populate_collection(
    tmp_path: Path,
    collection_name: str,
    n: int = 5,
    dim: int = FAKE_DIM,
) -> chromadb.Collection:
    """Create and populate a ChromaDB collection for testing."""
    client = chromadb.PersistentClient(path=str(tmp_path))
    col = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    ids = [f"doc-{i}" for i in range(n)]
    embeddings = [_fake_vector(i, dim) for i in range(n)]
    documents = [f"Alice: Message number {i} with some content" for i in range(n)]
    metadatas = [
        {
            "source_chat": "Alice & Bob",
            "chunk_index": i,
            "token_count": 10 + i,
            "message_count": 2,
            "attachment_count": 0,
            "contains_images": False,
            "contains_audio": False,
            "contains_video": False,
            "contains_documents": False,
            "embedding_model": "BAAI/bge-m3",
            "schema_version": "1.0.0",
        }
        for i in range(n)
    ]
    col.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    return col


# ===========================================================================
# 1. RetrievedDocument model tests
# ===========================================================================

class TestRetrievedDocument:

    def _valid(self, **overrides):
        base = dict(
            document_id="doc-1",
            text="Alice: Hello world",
            metadata={"source_chat": "Alice & Bob"},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="test_col",
            query="hello",
        )
        base.update(overrides)
        return RetrievedDocument(**base)

    def test_valid_creation(self):
        doc = self._valid()
        assert doc.rank == 1
        assert doc.similarity_score == 0.9

    def test_frozen(self):
        import dataclasses
        doc = self._valid()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            doc.text = "changed"  # type: ignore

    def test_empty_document_id_raises(self):
        with pytest.raises(ValueError, match="document_id"):
            self._valid(document_id="")

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="text"):
            self._valid(text="")

    def test_whitespace_only_text_raises(self):
        with pytest.raises(ValueError, match="text"):
            self._valid(text="   ")

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError, match="distance"):
            self._valid(distance=-0.1)

    def test_similarity_above_one_raises(self):
        with pytest.raises(ValueError, match="similarity_score"):
            self._valid(similarity_score=1.1)

    def test_similarity_below_zero_raises(self):
        with pytest.raises(ValueError, match="similarity_score"):
            self._valid(similarity_score=-0.1)

    def test_zero_rank_raises(self):
        with pytest.raises(ValueError, match="rank"):
            self._valid(rank=0)

    def test_negative_rank_raises(self):
        with pytest.raises(ValueError, match="rank"):
            self._valid(rank=-1)

    def test_empty_source_collection_raises(self):
        with pytest.raises(ValueError, match="source_collection"):
            self._valid(source_collection="")

    def test_metadata_must_be_dict(self):
        with pytest.raises(TypeError, match="metadata"):
            self._valid(metadata="not a dict")  # type: ignore

    def test_repr_contains_rank_and_score(self):
        doc = self._valid()
        r = repr(doc)
        assert "rank=1" in r
        assert "score=" in r


# ===========================================================================
# 2. RetrievalConfig tests
# ===========================================================================

class TestRetrievalConfig:

    def test_default_config(self):
        config = RetrievalConfig()
        assert config.top_k == 5
        assert config.score_threshold == 0.0
        assert config.distance_metric == "cosine"
        assert config.include_metadata is True
        assert config.include_documents is True
        assert config.enable_metadata_filtering is True

    def test_custom_values(self, tmp_path):
        config = RetrievalConfig(
            collection_name="my_col",
            persist_directory=str(tmp_path),
            top_k=10,
            score_threshold=0.5,
            distance_metric="l2",
        )
        assert config.top_k == 10
        assert config.score_threshold == 0.5
        assert config.distance_metric == "l2"

    def test_empty_collection_name_raises(self):
        with pytest.raises(ValueError, match="collection_name"):
            RetrievalConfig(collection_name="")

    def test_zero_top_k_raises(self):
        with pytest.raises(ValueError, match="top_k"):
            RetrievalConfig(top_k=0)

    def test_score_threshold_above_one_raises(self):
        with pytest.raises(ValueError, match="score_threshold"):
            RetrievalConfig(score_threshold=1.5)

    def test_score_threshold_below_zero_raises(self):
        with pytest.raises(ValueError, match="score_threshold"):
            RetrievalConfig(score_threshold=-0.1)

    def test_invalid_distance_metric_raises(self):
        with pytest.raises(ValueError, match="distance_metric"):
            RetrievalConfig(distance_metric="manhattan")

    def test_persist_path_is_pathlib(self, tmp_path):
        config = _make_retrieval_config(tmp_path)
        assert isinstance(config.persist_path, Path)

    def test_repr_contains_collection(self, tmp_path):
        config = _make_retrieval_config(tmp_path, "repr_col")
        assert "repr_col" in repr(config)


# ===========================================================================
# 3. QueryPreprocessor tests
# ===========================================================================

class TestQueryPreprocessor:

    def test_strips_leading_trailing_whitespace(self):
        assert QueryPreprocessor.preprocess("  hello  ") == "hello"

    def test_collapses_interior_spaces(self):
        assert QueryPreprocessor.preprocess("hello   world") == "hello world"

    def test_collapses_tabs(self):
        assert QueryPreprocessor.preprocess("hello\t\tworld") == "hello world"

    def test_normalises_windows_newline_to_space(self):
        result = QueryPreprocessor.preprocess("hello\r\nworld")
        assert "\r" not in result
        assert "\n" not in result
        assert "hello" in result
        assert "world" in result

    def test_normalises_bare_newline_to_space(self):
        result = QueryPreprocessor.preprocess("hello\nworld")
        assert "\n" not in result

    def test_nfc_unicode_normalisation(self):
        # e + combining accent → é (precomposed)
        decomposed = "cafe\u0301"
        result = QueryPreprocessor.preprocess(decomposed)
        assert result == "caf\u00e9"

    def test_empty_string_raises(self):
        with pytest.raises(QueryValidationError):
            QueryPreprocessor.preprocess("")

    def test_whitespace_only_raises(self):
        with pytest.raises(QueryValidationError):
            QueryPreprocessor.preprocess("   ")

    def test_non_string_raises(self):
        with pytest.raises(QueryValidationError):
            QueryPreprocessor.preprocess(None)  # type: ignore

    def test_integer_raises(self):
        with pytest.raises(QueryValidationError):
            QueryPreprocessor.preprocess(42)  # type: ignore

    def test_valid_query_unchanged_semantics(self):
        query = "What did Alice say about the project deadline?"
        result = QueryPreprocessor.preprocess(query)
        assert result == query

    def test_is_valid_true_for_valid_query(self):
        assert QueryPreprocessor.is_valid("hello world") is True

    def test_is_valid_false_for_empty(self):
        assert QueryPreprocessor.is_valid("") is False

    def test_preserves_emoji(self):
        result = QueryPreprocessor.preprocess("Hello 😀 world")
        assert "😀" in result

    def test_preserves_arabic(self):
        result = QueryPreprocessor.preprocess("مرحبا بالعالم")
        assert "مرحبا" in result


# ===========================================================================
# 4. QueryEmbedder tests (using FakeQueryEmbedder — no model weights)
# ===========================================================================

class TestQueryEmbedder:

    def test_embed_returns_list_of_floats(self):
        embedder = FakeQueryEmbedder()
        result = embedder.embed("hello world")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_embed_returns_correct_dimension(self):
        embedder = FakeQueryEmbedder(dim=FAKE_DIM)
        result = embedder.embed("test query")
        assert len(result) == FAKE_DIM

    def test_embed_deterministic_same_query(self):
        embedder = FakeQueryEmbedder()
        v1 = embedder.embed("same query")
        v2 = embedder.embed("same query")
        assert v1 == v2

    def test_embed_different_queries_different_vectors(self):
        embedder = FakeQueryEmbedder()
        v1 = embedder.embed("query one")
        v2 = embedder.embed("query two")
        assert v1 != v2

    def test_embed_fail_raises_query_embedding_error(self):
        embedder = FakeQueryEmbedder(should_fail=True)
        with pytest.raises(QueryEmbeddingError):
            embedder.embed("test")

    def test_embed_empty_string_raises(self):
        embedder = FakeQueryEmbedder()
        with pytest.raises(QueryEmbeddingError):
            embedder.embed("")

    def test_real_embedder_empty_query_raises(self):
        """QueryEmbedder.embed() must reject empty without loading model."""
        from app.retrieval.query_embedder import QueryEmbedder
        embedder = QueryEmbedder()
        # Inject a mock model so no weights load
        mock_model = MagicMock()
        mock_model.embed_text.side_effect = Exception("should not be called")
        embedder._model = mock_model
        with pytest.raises(QueryEmbeddingError):
            embedder.embed("")

    def test_real_embedder_wraps_model_failure(self):
        from app.retrieval.query_embedder import QueryEmbedder
        from exceptions.exceptions import EmbeddingGenerationError
        embedder = QueryEmbedder()
        mock_model = MagicMock()
        mock_model.embed_text.side_effect = EmbeddingGenerationError("model fail")
        embedder._model = mock_model
        with pytest.raises(QueryEmbeddingError, match="model fail"):
            embedder.embed("some query text")


# ===========================================================================
# 5. MetadataFilter tests
# ===========================================================================

class TestMetadataFilter:

    def test_none_returns_none(self):
        assert MetadataFilter().build(None) is None

    def test_empty_dict_returns_none(self):
        assert MetadataFilter().build({}) is None

    def test_single_equality_condition(self):
        where = MetadataFilter().build({"source_chat": "Alice & Bob"})
        assert where == {"source_chat": {"$eq": "Alice & Bob"}}

    def test_bool_field(self):
        where = MetadataFilter().build({"contains_images": True})
        assert where == {"contains_images": {"$eq": True}}

    def test_int_field(self):
        where = MetadataFilter().build({"chunk_index": 3})
        assert where == {"chunk_index": {"$eq": 3}}

    def test_multiple_conditions_produce_and(self):
        where = MetadataFilter().build(
            {"source_chat": "Alice & Bob", "contains_images": False}
        )
        assert "$and" in where
        assert len(where["$and"]) == 2

    def test_operator_gte(self):
        where = MetadataFilter().build({"chunk_index": {"$gte": 3}})
        assert where == {"chunk_index": {"$gte": 3}}

    def test_operator_ne(self):
        where = MetadataFilter().build({"source_chat": {"$ne": "SYSTEM"}})
        assert where == {"source_chat": {"$ne": "SYSTEM"}}

    def test_unknown_field_raises(self):
        with pytest.raises(MetadataFilterError, match="Unsupported"):
            MetadataFilter().build({"nonexistent_field": "value"})

    def test_unsupported_operator_raises(self):
        with pytest.raises(MetadataFilterError, match="Unsupported operator"):
            MetadataFilter().build({"chunk_index": {"$regex": ".*"}})

    def test_numeric_operator_on_string_field_raises(self):
        with pytest.raises(MetadataFilterError, match="numeric"):
            MetadataFilter().build({"source_chat": {"$gt": "Alice"}})

    def test_wrong_type_for_bool_field_raises(self):
        with pytest.raises(MetadataFilterError, match="bool"):
            MetadataFilter().build({"contains_images": "yes"})

    def test_wrong_type_for_str_field_raises(self):
        with pytest.raises(MetadataFilterError, match="str"):
            MetadataFilter().build({"source_chat": 42})

    def test_non_dict_raises(self):
        with pytest.raises(MetadataFilterError, match="dict"):
            MetadataFilter().build("not a dict")  # type: ignore

    def test_supported_fields_returns_list(self):
        fields = MetadataFilter.supported_fields()
        assert isinstance(fields, list)
        assert "source_chat" in fields
        assert "contains_images" in fields
        assert len(fields) >= 10

    def test_operator_dict_with_two_keys_raises(self):
        with pytest.raises(MetadataFilterError, match="exactly one"):
            MetadataFilter().build({"chunk_index": {"$gt": 1, "$lt": 5}})


# ===========================================================================
# 6. SimilaritySearch tests (real ChromaDB, tmp_path)
# ===========================================================================

class TestSimilaritySearch:

    def _searcher(self, tmp_path, collection, top_k=5, threshold=0.0):
        config = RetrievalConfig(
            collection_name=collection.name,
            persist_directory=str(tmp_path),
            top_k=top_k,
            score_threshold=threshold,
            distance_metric="cosine",
        )
        return SimilaritySearch(config=config, collection=collection)

    def test_returns_results_for_populated_collection(self, tmp_path):
        col = _populate_collection(tmp_path, "search_col1")
        searcher = self._searcher(tmp_path, col)
        results = searcher.search(_fake_vector(0), "test query")
        assert len(results) > 0

    def test_results_are_retrieved_documents(self, tmp_path):
        col = _populate_collection(tmp_path, "search_col2")
        searcher = self._searcher(tmp_path, col)
        results = searcher.search(_fake_vector(0), "test query")
        assert all(isinstance(r, RetrievedDocument) for r in results)

    def test_results_ordered_by_score_descending(self, tmp_path):
        col = _populate_collection(tmp_path, "search_col3", n=5)
        searcher = self._searcher(tmp_path, col, top_k=5)
        results = searcher.search(_fake_vector(0), "test query")
        scores = [r.similarity_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_rank_starts_at_one(self, tmp_path):
        col = _populate_collection(tmp_path, "search_col4")
        searcher = self._searcher(tmp_path, col, top_k=3)
        results = searcher.search(_fake_vector(0), "test query")
        if results:
            assert results[0].rank == 1

    def test_rank_is_sequential(self, tmp_path):
        col = _populate_collection(tmp_path, "search_col5", n=5)
        searcher = self._searcher(tmp_path, col, top_k=5)
        results = searcher.search(_fake_vector(0), "test query")
        ranks = [r.rank for r in results]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_empty_collection_returns_empty_list(self, tmp_path):
        client = chromadb.PersistentClient(path=str(tmp_path))
        col = client.get_or_create_collection(
            "empty_col", metadata={"hnsw:space": "cosine"}
        )
        config = RetrievalConfig(
            collection_name="empty_col",
            persist_directory=str(tmp_path),
        )
        searcher = SimilaritySearch(config=config, collection=col)
        results = searcher.search(_fake_vector(0), "test query")
        assert results == []

    def test_score_threshold_filters_low_scores(self, tmp_path):
        col = _populate_collection(tmp_path, "thresh_col", n=5)
        # Set threshold very high — should filter out most results
        searcher = self._searcher(tmp_path, col, top_k=5, threshold=0.99)
        results = searcher.search(_fake_vector(9), "test query")
        assert all(r.similarity_score >= 0.99 for r in results)

    def test_zero_threshold_returns_all_top_k(self, tmp_path):
        col = _populate_collection(tmp_path, "thresh_col2", n=5)
        searcher = self._searcher(tmp_path, col, top_k=5, threshold=0.0)
        results = searcher.search(_fake_vector(0), "test query")
        assert len(results) == 5

    def test_query_text_stored_on_results(self, tmp_path):
        col = _populate_collection(tmp_path, "query_text_col")
        searcher = self._searcher(tmp_path, col)
        results = searcher.search(_fake_vector(0), "my search query")
        for r in results:
            assert r.query == "my search query"

    def test_source_collection_set_on_results(self, tmp_path):
        col = _populate_collection(tmp_path, "src_col_test")
        config = RetrievalConfig(
            collection_name="src_col_test",
            persist_directory=str(tmp_path),
        )
        searcher = SimilaritySearch(config=config, collection=col)
        results = searcher.search(_fake_vector(0), "query")
        for r in results:
            assert r.source_collection == "src_col_test"

    def test_similarity_scores_in_unit_range(self, tmp_path):
        col = _populate_collection(tmp_path, "score_range_col", n=5)
        searcher = self._searcher(tmp_path, col, top_k=5)
        results = searcher.search(_fake_vector(0), "test")
        for r in results:
            assert 0.0 <= r.similarity_score <= 1.0

    def test_top_k_limits_results(self, tmp_path):
        col = _populate_collection(tmp_path, "topk_col", n=10)
        searcher = self._searcher(tmp_path, col, top_k=3)
        results = searcher.search(_fake_vector(0), "test query")
        assert len(results) <= 3

    def test_distance_cosine_to_similarity(self):
        config = RetrievalConfig(distance_metric="cosine")
        s = SimilaritySearch(config=config)
        assert s._distance_to_similarity(0.0) == pytest.approx(1.0)
        assert s._distance_to_similarity(1.0) == pytest.approx(0.0)
        assert s._distance_to_similarity(2.0) == pytest.approx(0.0)  # clamped

    def test_distance_l2_to_similarity(self):
        config = RetrievalConfig(distance_metric="l2")
        s = SimilaritySearch(config=config)
        assert s._distance_to_similarity(0.0) == pytest.approx(1.0)
        assert s._distance_to_similarity(1.0) == pytest.approx(0.5)

    def test_metadata_filter_applied(self, tmp_path):
        """Search with a where clause that restricts results."""
        col = _populate_collection(tmp_path, "filter_col", n=5)
        config = RetrievalConfig(
            collection_name="filter_col",
            persist_directory=str(tmp_path),
            top_k=5,
        )
        searcher = SimilaritySearch(config=config, collection=col)
        # Only chunk_index == 2 should match
        where = {"chunk_index": {"$eq": 2}}
        results = searcher.search(_fake_vector(0), "query", where=where)
        for r in results:
            assert r.metadata.get("chunk_index") == 2


# ===========================================================================
# 7. RetrievalPipeline integration tests (real ChromaDB, fake embedder)
# ===========================================================================

class TestRetrievalPipeline:

    def _pipeline(
        self,
        tmp_path,
        collection,
        top_k=5,
        threshold=0.0,
        should_fail=False,
    ):
        config = RetrievalConfig(
            collection_name=collection.name,
            persist_directory=str(tmp_path),
            top_k=top_k,
            score_threshold=threshold,
            distance_metric="cosine",
        )
        embedder = FakeQueryEmbedder(should_fail=should_fail)
        searcher = SimilaritySearch(config=config, collection=collection)
        return RetrievalPipeline(
            config=config, embedder=embedder, similarity_search=searcher
        )

    def test_search_returns_retrieved_documents(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col1")
        pipeline = self._pipeline(tmp_path, col)
        results = pipeline.search("What did Alice say?")
        assert isinstance(results, list)
        assert all(isinstance(r, RetrievedDocument) for r in results)

    def test_empty_query_raises_query_validation_error(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col2")
        pipeline = self._pipeline(tmp_path, col)
        with pytest.raises(QueryValidationError):
            pipeline.search("")

    def test_whitespace_only_query_raises(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col3")
        pipeline = self._pipeline(tmp_path, col)
        with pytest.raises(QueryValidationError):
            pipeline.search("   ")

    def test_query_preprocessed_before_embed(self, tmp_path):
        """Leading/trailing whitespace must be stripped before embedding."""
        col = _populate_collection(tmp_path, "pipe_col4")
        config = RetrievalConfig(
            collection_name=col.name,
            persist_directory=str(tmp_path),
        )
        embedder = FakeQueryEmbedder()
        searcher = SimilaritySearch(config=config, collection=col)
        pipeline = RetrievalPipeline(
            config=config, embedder=embedder, similarity_search=searcher
        )
        results = pipeline.search("  hello world  ")
        # query on results should be stripped
        for r in results:
            assert r.query == "hello world"

    def test_embedder_failure_raises_query_embedding_error(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col5")
        pipeline = self._pipeline(tmp_path, col, should_fail=True)
        with pytest.raises(QueryEmbeddingError):
            pipeline.search("valid query")

    def test_multiple_results_ranked(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col6", n=5)
        pipeline = self._pipeline(tmp_path, col, top_k=5)
        results = pipeline.search("Alice message")
        assert len(results) > 0
        ranks = [r.rank for r in results]
        assert ranks[0] == 1

    def test_metadata_filter_via_pipeline(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col7", n=5)
        pipeline = self._pipeline(tmp_path, col, top_k=5)
        results = pipeline.search("query", filters={"chunk_index": 1})
        for r in results:
            assert r.metadata.get("chunk_index") == 1

    def test_metadata_filter_disabled_ignores_filters(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col8", n=5)
        config = RetrievalConfig(
            collection_name=col.name,
            persist_directory=str(tmp_path),
            top_k=5,
            enable_metadata_filtering=False,
        )
        embedder = FakeQueryEmbedder()
        searcher = SimilaritySearch(config=config, collection=col)
        pipeline = RetrievalPipeline(
            config=config, embedder=embedder, similarity_search=searcher
        )
        # Even with a strict filter, should return results (filter ignored)
        results = pipeline.search("query", filters={"chunk_index": 99999})
        # Filter ignored, so should still find results
        assert isinstance(results, list)

    def test_high_threshold_may_return_empty(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col9", n=3)
        pipeline = self._pipeline(tmp_path, col, top_k=5, threshold=0.9999)
        results = pipeline.search("a very random query xyz")
        # May be empty — that's fine; must not raise
        assert isinstance(results, list)

    def test_close_does_not_raise(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col10")
        pipeline = self._pipeline(tmp_path, col)
        pipeline.close()  # must not raise

    def test_invalid_filter_field_raises_metadata_filter_error(self, tmp_path):
        col = _populate_collection(tmp_path, "pipe_col11")
        pipeline = self._pipeline(tmp_path, col)
        with pytest.raises(MetadataFilterError):
            pipeline.search("query", filters={"bad_field": "value"})

    def test_no_rag_no_answer_generation(self, tmp_path):
        """Phase 5 must NOT generate answers — results are raw documents."""
        col = _populate_collection(tmp_path, "no_rag_col")
        pipeline = self._pipeline(tmp_path, col)
        results = pipeline.search("What happened?")
        # Every result is a RetrievedDocument — no answer string anywhere
        for r in results:
            assert isinstance(r, RetrievedDocument)
            assert not hasattr(r, "answer")
            assert not hasattr(r, "generated_text")


# ===========================================================================
# 8. Exception type tests
# ===========================================================================

class TestExceptionTypes:

    def test_retrieval_error(self):
        err = RetrievalError("retrieval failed")
        assert isinstance(err, Exception)
        assert str(err) == "retrieval failed"

    def test_query_validation_error(self):
        err = QueryValidationError("empty query")
        assert isinstance(err, Exception)

    def test_query_embedding_error(self):
        err = QueryEmbeddingError("embed fail")
        assert isinstance(err, Exception)

    def test_similarity_search_error(self):
        err = SimilaritySearchError("search fail")
        assert isinstance(err, Exception)

    def test_metadata_filter_error(self):
        err = MetadataFilterError("bad field")
        assert isinstance(err, Exception)
