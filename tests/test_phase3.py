"""
tests/test_phase3.py — Comprehensive unit tests for Phase 3.

CRITICAL DESIGN DECISION: No real model weights are downloaded.
============================================================
Every test that touches EmbeddingModel injects a MockEmbeddingModel.
The mock:
  • Returns deterministic fake vectors of the correct dimension.
  • Raises on demand to test error handling.
  • Records call counts for cache-hit verification.

This makes the entire test suite runnable in < 2 seconds with no network
access and no GPU, while still exercising every code path in production.
"""

from __future__ import annotations

import math
import pytest
from typing import List
from unittest.mock import MagicMock, patch

from models.document import Document, make_document_id
from models.embedded_document import EmbeddedDocument, embedding_to_tuple, utc_now_iso

from app.vectorization.embedding_model import EmbeddingModel, DEFAULT_MODEL_NAME
from app.vectorization.embedding_cache import EmbeddingCache
from app.vectorization.embedding_generator import EmbeddingGenerator
from app.vectorization.embedding_batcher import EmbeddingBatcher
from app.vectorization.embedding_pipeline import EmbeddingPipeline

from exceptions.exceptions import (
    EmbeddingModelError,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    CacheError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAKE_DIM = 8   # small dimension — fast, deterministic, still exercises all code


# ---------------------------------------------------------------------------
# Mock embedding model
# ---------------------------------------------------------------------------

class MockEmbeddingModel(EmbeddingModel):
    """
    Test double for EmbeddingModel.

    Bypasses the singleton and never loads real model weights.
    Returns normalised fake vectors deterministically derived from the
    hash of the input text, so identical texts → identical vectors.
    """

    def __new__(cls, *args, **kwargs):
        # Bypass the singleton (__new__ would otherwise return the same instance)
        instance = object.__new__(cls)
        instance._initialised = False
        return instance

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device=None,
        dim: int = FAKE_DIM,
        should_fail: bool = False,
    ) -> None:
        # Do NOT call super().__init__() — avoids loading real model
        self._model_name = model_name
        self._device = device
        self._model = MagicMock()   # never called directly; we override methods
        self._dim = dim
        self._should_fail = should_fail
        self._embed_text_calls = 0
        self._embed_batch_calls = 0
        self._initialised = True

    @property
    def is_loaded(self) -> bool:
        return True

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def embed_text(self, text: str) -> List[float]:
        if self._should_fail:
            raise EmbeddingGenerationError("Mock model failure (embed_text).")
        if not text or not text.strip():
            raise EmbeddingGenerationError("Cannot embed empty string.")
        self._embed_text_calls += 1
        return _fake_vector(text, self._dim)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self._should_fail:
            raise EmbeddingGenerationError("Mock model failure (embed_batch).")
        self._embed_batch_calls += 1
        return [_fake_vector(t, self._dim) for t in texts]


def _fake_vector(text: str, dim: int) -> List[float]:
    """
    Produce a deterministic L2-normalised fake vector from *text*.

    Uses the hash of the text to seed values, then L2-normalises so the
    vector behaves exactly like a real normalised embedding.
    """
    import hashlib
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
    raw = [(((seed >> (i * 4)) & 0xF) - 7.5) / 7.5 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_doc(
    doc_id: str = None,
    text: str = "Alice: Hello world",
    chunk_index: int = 0,
    token_count: int = 5,
    participants: tuple = ("Alice",),
    attachments: tuple = (),
    message_ids: tuple = (1,),
    metadata: dict = None,
    source_chat: str = "Test Chat",
    start_ts: str = "1/1/2024, 9:00 AM",
    end_ts: str = "1/1/2024, 9:05 AM",
) -> Document:
    return Document(
        id=doc_id or make_document_id(),
        text=text,
        metadata=metadata or {"message_count": 1},
        participants=participants,
        attachments=attachments,
        message_ids=message_ids,
        source_chat=source_chat,
        chunk_index=chunk_index,
        token_count=token_count,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
    )


def _make_generator(dim: int = FAKE_DIM, cache=None, fail=False):
    model = MockEmbeddingModel(dim=dim, should_fail=fail)
    return EmbeddingGenerator(model=model, cache=cache)


def _make_batcher(dim: int = FAKE_DIM, cache=None, batch_size=4, fail=False):
    model = MockEmbeddingModel(dim=dim, should_fail=fail)
    return EmbeddingBatcher(model=model, cache=cache, batch_size=batch_size)


# ===========================================================================
# 1. EmbeddedDocument model tests
# ===========================================================================

class TestEmbeddedDocumentModel:

    def _valid_kwargs(self, dim=FAKE_DIM):
        vec = _fake_vector("hello", dim)
        return dict(
            document_id="doc-1",
            text="Alice: Hello",
            embedding=tuple(vec),
            metadata={"x": 1},
            token_count=5,
            model_name="BAAI/bge-m3",
            embedding_dim=dim,
            created_at=utc_now_iso(),
        )

    def test_valid_creation(self):
        doc = EmbeddedDocument(**self._valid_kwargs())
        assert doc.document_id == "doc-1"
        assert doc.embedding_dim == FAKE_DIM
        assert len(doc.embedding) == FAKE_DIM

    def test_frozen(self):
        import dataclasses
        doc = EmbeddedDocument(**self._valid_kwargs())
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            doc.text = "changed"  # type: ignore

    def test_empty_document_id_raises(self):
        kw = self._valid_kwargs()
        kw["document_id"] = ""
        with pytest.raises(ValueError, match="document_id"):
            EmbeddedDocument(**kw)

    def test_empty_embedding_raises(self):
        kw = self._valid_kwargs()
        kw["embedding"] = ()
        kw["embedding_dim"] = 0
        with pytest.raises(ValueError):
            EmbeddedDocument(**kw)

    def test_nan_in_embedding_raises(self):
        kw = self._valid_kwargs()
        vec = list(kw["embedding"])
        vec[0] = float("nan")
        kw["embedding"] = tuple(vec)
        with pytest.raises(ValueError, match="NaN"):
            EmbeddedDocument(**kw)

    def test_inf_in_embedding_raises(self):
        kw = self._valid_kwargs()
        vec = list(kw["embedding"])
        vec[0] = float("inf")
        kw["embedding"] = tuple(vec)
        with pytest.raises(ValueError, match="Inf"):
            EmbeddedDocument(**kw)

    def test_dimension_mismatch_raises(self):
        kw = self._valid_kwargs()
        kw["embedding_dim"] = 999
        with pytest.raises(ValueError, match="embedding_dim"):
            EmbeddedDocument(**kw)

    def test_negative_token_count_raises(self):
        kw = self._valid_kwargs()
        kw["token_count"] = -1
        with pytest.raises(ValueError, match="token_count"):
            EmbeddedDocument(**kw)

    def test_empty_model_name_raises(self):
        kw = self._valid_kwargs()
        kw["model_name"] = ""
        with pytest.raises(ValueError, match="model_name"):
            EmbeddedDocument(**kw)

    def test_empty_created_at_raises(self):
        kw = self._valid_kwargs()
        kw["created_at"] = ""
        with pytest.raises(ValueError, match="created_at"):
            EmbeddedDocument(**kw)

    def test_is_normalised_true_for_unit_vector(self):
        doc = EmbeddedDocument(**self._valid_kwargs())
        assert doc.is_normalised is True

    def test_is_normalised_false_for_non_unit_vector(self):
        kw = self._valid_kwargs()
        kw["embedding"] = tuple([2.0] * FAKE_DIM)
        # recompute dim to match
        kw["embedding_dim"] = FAKE_DIM
        # NaN/Inf check passes, but norm ≠ 1
        doc = EmbeddedDocument(**kw)
        assert doc.is_normalised is False

    def test_metadata_is_dict(self):
        doc = EmbeddedDocument(**self._valid_kwargs())
        assert isinstance(doc.metadata, dict)

    def test_embedding_to_tuple_converts_list(self):
        lst = [1.0, 2.0, 3.0]
        result = embedding_to_tuple(lst)
        assert isinstance(result, tuple)
        assert result == (1.0, 2.0, 3.0)

    def test_embedding_to_tuple_empty_raises(self):
        with pytest.raises(ValueError):
            embedding_to_tuple([])


# ===========================================================================
# 2. EmbeddingCache tests
# ===========================================================================

class TestEmbeddingCache:

    def test_cache_miss_returns_none(self):
        cache = EmbeddingCache()
        assert cache.get("nonexistent_key") is None

    def test_cache_put_and_get(self):
        cache = EmbeddingCache()
        vec = [0.1, 0.2, 0.3]
        key = cache.compute_key("hello")
        cache.put(key, vec)
        assert cache.get(key) == vec

    def test_compute_key_is_deterministic(self):
        cache = EmbeddingCache()
        k1 = cache.compute_key("hello world")
        k2 = cache.compute_key("hello world")
        assert k1 == k2

    def test_compute_key_different_texts_different_keys(self):
        cache = EmbeddingCache()
        k1 = cache.compute_key("hello")
        k2 = cache.compute_key("world")
        assert k1 != k2

    def test_compute_key_is_64_chars(self):
        cache = EmbeddingCache()
        assert len(cache.compute_key("anything")) == 64

    def test_hit_counter_increments(self):
        cache = EmbeddingCache()
        key = cache.compute_key("text")
        cache.put(key, [0.1])
        cache.get(key)
        cache.get(key)
        assert cache.hits == 2

    def test_miss_counter_increments(self):
        cache = EmbeddingCache()
        cache.get("missing_key_1")
        cache.get("missing_key_2")
        assert cache.misses == 2

    def test_hit_rate_calculation(self):
        cache = EmbeddingCache()
        key = cache.compute_key("abc")
        cache.put(key, [1.0])
        cache.get(key)       # hit
        cache.get("missing") # miss
        assert cache.hit_rate == pytest.approx(0.5)

    def test_cache_size_reflects_entries(self):
        cache = EmbeddingCache()
        assert cache.size == 0
        cache.put(cache.compute_key("a"), [1.0])
        assert cache.size == 1
        cache.put(cache.compute_key("b"), [2.0])
        assert cache.size == 2

    def test_eviction_at_max_size(self):
        cache = EmbeddingCache(max_size=2)
        k1 = cache.compute_key("first")
        k2 = cache.compute_key("second")
        k3 = cache.compute_key("third")
        cache.put(k1, [1.0])
        cache.put(k2, [2.0])
        cache.put(k3, [3.0])  # should evict k1
        assert cache.size == 2
        assert cache.get(k1) is None  # evicted
        assert cache.get(k3) == [3.0]

    def test_invalidate_removes_entry(self):
        cache = EmbeddingCache()
        key = cache.compute_key("removeme")
        cache.put(key, [9.0])
        assert cache.invalidate(key) is True
        assert cache.get(key) is None

    def test_invalidate_nonexistent_returns_false(self):
        cache = EmbeddingCache()
        assert cache.invalidate("ghost") is False

    def test_clear_resets_everything(self):
        cache = EmbeddingCache()
        key = cache.compute_key("x")
        cache.put(key, [1.0])
        cache.get(key)
        cache.clear()
        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_put_empty_vector_raises(self):
        cache = EmbeddingCache()
        with pytest.raises(CacheError, match="empty"):
            cache.put("key", [])

    def test_put_non_list_raises(self):
        cache = EmbeddingCache()
        with pytest.raises(CacheError):
            cache.put("key", (1.0, 2.0))  # type: ignore

    def test_stats_returns_expected_keys(self):
        cache = EmbeddingCache()
        stats = cache.stats()
        assert "size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "max_size" in stats

    def test_max_size_one_raises_on_zero(self):
        with pytest.raises(ValueError):
            EmbeddingCache(max_size=0)


# ===========================================================================
# 3. EmbeddingGenerator tests
# ===========================================================================

class TestEmbeddingGenerator:

    def test_generates_embedded_document(self):
        doc = _make_doc()
        gen = _make_generator()
        result = gen.generate(doc)
        assert isinstance(result, EmbeddedDocument)

    def test_document_id_preserved(self):
        doc = _make_doc(doc_id="fixed-id-xyz")
        gen = _make_generator()
        result = gen.generate(doc)
        assert result.document_id == "fixed-id-xyz"

    def test_text_preserved(self):
        doc = _make_doc(text="Alice: Hello there")
        gen = _make_generator()
        result = gen.generate(doc)
        assert result.text == "Alice: Hello there"

    def test_token_count_preserved(self):
        doc = _make_doc(token_count=42)
        gen = _make_generator()
        result = gen.generate(doc)
        assert result.token_count == 42

    def test_embedding_has_correct_dimension(self):
        doc = _make_doc()
        gen = _make_generator(dim=FAKE_DIM)
        result = gen.generate(doc)
        assert result.embedding_dim == FAKE_DIM
        assert len(result.embedding) == FAKE_DIM

    def test_embedding_is_normalised(self):
        doc = _make_doc()
        gen = _make_generator()
        result = gen.generate(doc)
        assert result.is_normalised

    def test_metadata_extended_not_replaced(self):
        doc = _make_doc(metadata={"custom_key": "custom_value"})
        gen = _make_generator()
        result = gen.generate(doc)
        # Original metadata key preserved
        assert result.metadata.get("custom_key") == "custom_value"
        # New embedding metadata added
        assert "embedding_model" in result.metadata
        assert "embedding_dim" in result.metadata

    def test_source_chat_in_metadata(self):
        doc = _make_doc(source_chat="Alice & Bob")
        gen = _make_generator()
        result = gen.generate(doc)
        assert result.metadata["source_chat"] == "Alice & Bob"

    def test_participants_in_metadata(self):
        doc = _make_doc(participants=("Alice", "Bob"))
        gen = _make_generator()
        result = gen.generate(doc)
        assert set(result.metadata["participants"]) == {"Alice", "Bob"}

    def test_model_name_set_correctly(self):
        doc = _make_doc()
        model = MockEmbeddingModel(model_name="custom-model")
        gen = EmbeddingGenerator(model=model)
        result = gen.generate(doc)
        assert result.model_name == "custom-model"

    def test_created_at_is_non_empty_string(self):
        doc = _make_doc()
        gen = _make_generator()
        result = gen.generate(doc)
        assert isinstance(result.created_at, str)
        assert len(result.created_at) > 0

    def test_cache_hit_skips_model_call(self):
        cache = EmbeddingCache()
        model = MockEmbeddingModel(dim=FAKE_DIM)
        gen = EmbeddingGenerator(model=model, cache=cache)
        doc = _make_doc(text="unique text abc123")

        # First call — cache miss
        result1 = gen.generate(doc)
        calls_after_miss = model._embed_text_calls

        # Second call — should be cache hit
        result2 = gen.generate(doc)
        calls_after_hit = model._embed_text_calls

        # Model was called exactly once
        assert calls_after_miss == 1
        assert calls_after_hit == 1   # no additional call
        assert result1.embedding == result2.embedding

    def test_cache_miss_calls_model(self):
        model = MockEmbeddingModel(dim=FAKE_DIM)
        gen = EmbeddingGenerator(model=model, cache=None)
        doc = _make_doc()
        gen.generate(doc)
        assert model._embed_text_calls == 1

    def test_model_failure_raises_embedding_generation_error(self):
        doc = _make_doc()
        gen = _make_generator(fail=True)
        with pytest.raises(EmbeddingGenerationError):
            gen.generate(doc)

    def test_wrong_input_type_raises(self):
        gen = _make_generator()
        with pytest.raises(EmbeddingGenerationError):
            gen.generate("not a document")  # type: ignore

    def test_wrong_model_type_raises(self):
        with pytest.raises(TypeError):
            EmbeddingGenerator(model="not a model")  # type: ignore

    def test_empty_text_document_produces_zero_sentinel(self):
        doc = _make_doc(text="   ")
        gen = _make_generator()
        result = gen.generate(doc)
        # Should not raise; produces zero-vector sentinel
        assert isinstance(result, EmbeddedDocument)
        assert len(result.embedding) == FAKE_DIM


# ===========================================================================
# 4. EmbeddingBatcher tests
# ===========================================================================

class TestEmbeddingBatcher:

    def test_empty_input_returns_empty_list(self):
        batcher = _make_batcher()
        assert batcher.embed_all([]) == []

    def test_single_document_produces_one_embedded_document(self):
        batcher = _make_batcher()
        docs = [_make_doc()]
        results = batcher.embed_all(docs)
        assert len(results) == 1
        assert isinstance(results[0], EmbeddedDocument)

    def test_output_order_matches_input_order(self):
        batcher = _make_batcher(batch_size=2)
        docs = [_make_doc(doc_id=f"doc-{i}", text=f"Alice: message {i}") for i in range(6)]
        results = batcher.embed_all(docs)
        assert [r.document_id for r in results] == [f"doc-{i}" for i in range(6)]

    def test_batch_boundary_preserved(self):
        """batch_size=3 for 7 docs → batches of 3,3,1."""
        batcher = _make_batcher(batch_size=3)
        docs = [_make_doc(doc_id=f"d{i}", text=f"text {i}") for i in range(7)]
        results = batcher.embed_all(docs)
        assert len(results) == 7

    def test_all_results_are_embedded_documents(self):
        batcher = _make_batcher(batch_size=4)
        docs = [_make_doc(text=f"msg {i}") for i in range(10)]
        results = batcher.embed_all(docs)
        assert all(isinstance(r, EmbeddedDocument) for r in results)

    def test_all_embeddings_have_correct_dim(self):
        batcher = _make_batcher(dim=FAKE_DIM)
        docs = [_make_doc(text=f"text {i}") for i in range(5)]
        results = batcher.embed_all(docs)
        assert all(r.embedding_dim == FAKE_DIM for r in results)

    def test_duplicate_texts_only_embedded_once_with_cache(self):
        """When cache is enabled, two documents with identical text should
        result in the model being called only once."""
        cache = EmbeddingCache()
        model = MockEmbeddingModel(dim=FAKE_DIM)
        batcher = EmbeddingBatcher(model=model, cache=cache, batch_size=4)

        same_text = "Alice: Identical message content"
        docs = [_make_doc(doc_id=f"d{i}", text=same_text) for i in range(4)]
        results = batcher.embed_all(docs)

        assert len(results) == 4
        # All embeddings should be identical (same text → same vector)
        first_vec = results[0].embedding
        assert all(r.embedding == first_vec for r in results)
        # Model embed_batch was called exactly once (first doc missed cache)
        assert model._embed_batch_calls == 1

    def test_model_failure_propagates(self):
        batcher = _make_batcher(fail=True)
        docs = [_make_doc(text="some text")]
        with pytest.raises(EmbeddingGenerationError):
            batcher.embed_all(docs)

    def test_invalid_batch_size_raises(self):
        model = MockEmbeddingModel()
        with pytest.raises(ValueError, match="batch_size"):
            EmbeddingBatcher(model=model, batch_size=0)

    def test_wrong_model_type_raises(self):
        with pytest.raises(TypeError):
            EmbeddingBatcher(model="not a model", batch_size=4)  # type: ignore

    def test_cache_hit_rate_improves_with_duplicates(self):
        cache = EmbeddingCache()
        model = MockEmbeddingModel(dim=FAKE_DIM)
        batcher = EmbeddingBatcher(model=model, cache=cache, batch_size=2)
        text = "same message"
        # 4 docs with identical text; batch_size=2
        # Batch 1: both docs are cache misses → embed once, write cache
        # Batch 2: both docs find the cached vector → 2 hits
        docs = [_make_doc(doc_id=f"d{i}", text=text) for i in range(4)]
        batcher.embed_all(docs)
        # At least some cache hits must have occurred
        assert cache.hits >= 2

    def test_metadata_preserved_through_batcher(self):
        batcher = _make_batcher()
        docs = [_make_doc(metadata={"custom": "value"})]
        results = batcher.embed_all(docs)
        assert results[0].metadata.get("custom") == "value"

    def test_large_batch_produces_correct_count(self):
        batcher = _make_batcher(batch_size=16)
        docs = [_make_doc(text=f"message {i}") for i in range(100)]
        results = batcher.embed_all(docs)
        assert len(results) == 100


# ===========================================================================
# 5. EmbeddingPipeline integration tests
# ===========================================================================

class TestEmbeddingPipeline:

    def _pipeline(self, docs, dim=FAKE_DIM, cache=None, batch_size=4, fail=False):
        model = MockEmbeddingModel(dim=dim, should_fail=fail)
        return EmbeddingPipeline(
            documents=docs,
            model=model,
            cache=cache,
            batch_size=batch_size,
        )

    def test_empty_documents_returns_empty_list(self):
        pipeline = self._pipeline([])
        assert pipeline.run() == []

    def test_single_document_returns_one_embedded_document(self):
        docs = [_make_doc()]
        results = self._pipeline(docs).run()
        assert len(results) == 1
        assert isinstance(results[0], EmbeddedDocument)

    def test_output_is_list_of_embedded_documents(self):
        docs = [_make_doc(text=f"message {i}") for i in range(5)]
        results = self._pipeline(docs).run()
        assert isinstance(results, list)
        assert all(isinstance(r, EmbeddedDocument) for r in results)

    def test_output_count_matches_input_count(self):
        docs = [_make_doc(text=f"msg {i}") for i in range(10)]
        results = self._pipeline(docs).run()
        assert len(results) == 10

    def test_document_ids_preserved(self):
        ids = [f"id-{i}" for i in range(5)]
        docs = [_make_doc(doc_id=did, text=f"text {i}") for i, did in enumerate(ids)]
        results = self._pipeline(docs).run()
        assert [r.document_id for r in results] == ids

    def test_order_preserved(self):
        docs = [_make_doc(doc_id=f"d{i}", text=f"unique text {i} abc") for i in range(8)]
        results = self._pipeline(docs).run()
        assert [r.document_id for r in results] == [f"d{i}" for i in range(8)]

    def test_embeddings_have_correct_dimension(self):
        docs = [_make_doc(text=f"t{i}") for i in range(5)]
        results = self._pipeline(docs, dim=FAKE_DIM).run()
        assert all(r.embedding_dim == FAKE_DIM for r in results)

    def test_embeddings_are_normalised(self):
        docs = [_make_doc(text=f"hello {i}") for i in range(5)]
        results = self._pipeline(docs).run()
        assert all(r.is_normalised for r in results)

    def test_metadata_populated(self):
        docs = [_make_doc(metadata={"score": 99})]
        results = self._pipeline(docs).run()
        assert results[0].metadata.get("score") == 99
        assert "embedding_model" in results[0].metadata

    def test_cache_reduces_model_calls(self):
        cache = EmbeddingCache()
        model = MockEmbeddingModel(dim=FAKE_DIM)
        same_text = "Alice: same content everywhere"
        docs = [_make_doc(doc_id=f"d{i}", text=same_text) for i in range(6)]
        pipeline = EmbeddingPipeline(
            documents=docs, model=model, cache=cache, batch_size=4
        )
        pipeline.run()
        # 6 docs with identical text and batch_size=4 → batch 1 (4 docs) deduplicates
        # to 1 model call; batch 2 (2 docs) finds them in cache via Pass 1 → 0 calls.
        # Total embed_batch calls: 1 (for the first unique text in batch 1).
        assert model._embed_batch_calls == 1

    def test_invalid_documents_type_raises(self):
        with pytest.raises(TypeError):
            EmbeddingPipeline(documents="not a list")  # type: ignore

    def test_invalid_first_element_type_raises(self):
        with pytest.raises(TypeError):
            EmbeddingPipeline(documents=["not a document"])  # type: ignore

    def test_model_failure_propagates(self):
        docs = [_make_doc(text="real text")]
        pipeline = self._pipeline(docs, fail=True)
        with pytest.raises(EmbeddingGenerationError):
            pipeline.run()

    def test_unicode_and_emoji_documents(self):
        docs = [
            _make_doc(text="Alice: Hello 😀🎉"),
            _make_doc(text="Bob: Привет мир"),
            _make_doc(text="Carol: 你好世界"),
            _make_doc(text="Dave: مرحبا بالعالم"),
        ]
        results = self._pipeline(docs).run()
        assert len(results) == 4

    def test_pipeline_with_no_cache(self):
        model = MockEmbeddingModel(dim=FAKE_DIM)
        docs = [_make_doc(text=f"msg {i}") for i in range(5)]
        pipeline = EmbeddingPipeline(
            documents=docs, model=model, cache=None, batch_size=4
        )
        results = pipeline.run()
        assert len(results) == 5

    def test_pipeline_with_default_cache(self):
        """Omitting cache argument should create a default EmbeddingCache."""
        model = MockEmbeddingModel(dim=FAKE_DIM)
        docs = [_make_doc(text="hello")]
        # cache sentinel → default EmbeddingCache created inside pipeline
        pipeline = EmbeddingPipeline(documents=docs, model=model, batch_size=4)
        results = pipeline.run()
        assert len(results) == 1

    def test_large_corpus(self):
        """100 documents with batch_size=16 should complete without error."""
        docs = [_make_doc(text=f"Document number {i} with some content") for i in range(100)]
        results = self._pipeline(docs, batch_size=16).run()
        assert len(results) == 100

    def test_attachment_metadata_preserved(self):
        doc = _make_doc(
            metadata={"contains_images": True, "attachment_count": 1},
            attachments=("photo.jpg",),
        )
        results = self._pipeline([doc]).run()
        assert results[0].metadata.get("contains_images") is True
        assert results[0].metadata.get("attachment_count") == 1

    def test_token_counts_preserved(self):
        docs = [_make_doc(token_count=i * 10 + 5) for i in range(4)]
        results = self._pipeline(docs).run()
        assert [r.token_count for r in results] == [5, 15, 25, 35]

    def test_source_chat_in_metadata(self):
        doc = _make_doc(source_chat="Alice & Bob")
        results = self._pipeline([doc]).run()
        assert results[0].metadata.get("source_chat") == "Alice & Bob"


# ===========================================================================
# 6. Error handling tests
# ===========================================================================

class TestErrorHandling:

    def test_embedding_validation_error_nan_in_generator(self):
        """Manually produce a NaN vector and verify validation catches it."""
        model = MockEmbeddingModel(dim=FAKE_DIM)
        gen = EmbeddingGenerator(model=model, cache=None)

        # Patch embed_text to return NaN
        original = model.embed_text
        model.embed_text = lambda text: [float("nan")] * FAKE_DIM

        doc = _make_doc(text="trigger nan")
        with pytest.raises(EmbeddingValidationError, match="NaN"):
            gen.generate(doc)

        model.embed_text = original

    def test_embedding_validation_error_zero_norm(self):
        """A zero-vector has zero norm and must be rejected."""
        model = MockEmbeddingModel(dim=FAKE_DIM)
        gen = EmbeddingGenerator(model=model, cache=None)
        model.embed_text = lambda text: [0.0] * FAKE_DIM

        doc = _make_doc(text="trigger zero norm")
        with pytest.raises(EmbeddingValidationError, match="zero norm"):
            gen.generate(doc)

    def test_cache_error_on_non_list_put(self):
        cache = EmbeddingCache()
        with pytest.raises(CacheError):
            cache.put("key", (1.0, 2.0))  # type: ignore

    def test_embedding_model_error_type(self):
        """EmbeddingModelError is importable and is an Exception subclass."""
        err = EmbeddingModelError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_embedding_generation_error_type(self):
        err = EmbeddingGenerationError("gen error")
        assert isinstance(err, Exception)

    def test_embedding_validation_error_type(self):
        err = EmbeddingValidationError("val error")
        assert isinstance(err, Exception)

    def test_cache_error_type(self):
        err = CacheError("cache error")
        assert isinstance(err, Exception)
