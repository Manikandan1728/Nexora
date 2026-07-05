"""
tests/test_phase6_m3.py — Unit tests for CitationBuilder and AnswerGenerator.

No real LLM calls.  All providers are fake test doubles.
"""

from __future__ import annotations

import pytest
from typing import List
from unittest.mock import MagicMock

from models.retrieved_document import RetrievedDocument
from models.answer import Citation, GroundedAnswer
from llm.interfaces import ILLMProvider, LLMResponse
from app.generation.citation_builder import CitationBuilder
from app.generation.answer_generator import AnswerGenerator
from exceptions.exceptions import CitationError, AnswerGenerationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(
    rank: int = 1,
    text: str = "Alice: Hello world",
    doc_id: str = None,
    score: float = 0.85,
    source_chat: str = "Alice & Bob",
    chunk_index: int = 2,
    start_ts: str = "1/1/2024, 9:00 AM",
    end_ts: str = "1/1/2024, 9:05 AM",
) -> RetrievedDocument:
    return RetrievedDocument(
        document_id=doc_id or f"doc-{rank:03d}",
        text=text,
        metadata={
            "source_chat":     source_chat,
            "chunk_index":     chunk_index,
            "start_timestamp": start_ts,
            "end_timestamp":   end_ts,
        },
        distance=1.0 - score,
        similarity_score=score,
        rank=rank,
        source_collection="test_col",
        query="test query",
    )


class FakeProvider(ILLMProvider):
    """Test double — returns deterministic responses without any API call."""

    def __init__(
        self,
        text: str = "The answer is 42.",
        tokens: int = 30,
        model: str = "fake-model",
        provider: str = "fake",
        should_fail: bool = False,
    ):
        self._text = text
        self._tokens = tokens
        self._model = model
        self._provider_name = provider
        self._should_fail = should_fail
        self._closed = False
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        if self._should_fail:
            from exceptions.exceptions import LLMProviderError
            raise LLMProviderError("FakeProvider forced failure.")
        self.call_count += 1
        return LLMResponse(
            text=self._text,
            tokens_used=self._tokens,
            model=self._model,
            provider=self._provider_name,
        )

    def health_check(self) -> bool:
        return not self._should_fail

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def close(self) -> None:
        self._closed = True


# ===========================================================================
# 1. CitationBuilder tests
# ===========================================================================

class TestCitationBuilder:

    def test_returns_tuple(self):
        cb = CitationBuilder()
        result = cb.build([_make_doc(1)])
        assert isinstance(result, tuple)

    def test_one_citation_per_document(self):
        cb = CitationBuilder()
        docs = [_make_doc(i) for i in range(1, 4)]
        result = cb.build(docs)
        assert len(result) == 3

    def test_rank_order_preserved(self):
        cb = CitationBuilder()
        docs = [_make_doc(1), _make_doc(2), _make_doc(3)]
        result = cb.build(docs)
        ranks = [c.rank for c in result]
        assert ranks == [1, 2, 3]

    def test_document_id_mapped(self):
        cb = CitationBuilder()
        result = cb.build([_make_doc(1, doc_id="abc-xyz")])
        assert result[0].document_id == "abc-xyz"

    def test_similarity_score_mapped(self):
        cb = CitationBuilder()
        result = cb.build([_make_doc(1, score=0.9876)])
        assert result[0].similarity_score == pytest.approx(0.9876)

    def test_source_chat_mapped(self):
        cb = CitationBuilder()
        result = cb.build([_make_doc(1, source_chat="Alice & Carol")])
        assert result[0].source_chat == "Alice & Carol"

    def test_chunk_index_mapped(self):
        cb = CitationBuilder()
        result = cb.build([_make_doc(1, chunk_index=7)])
        assert result[0].chunk_index == 7

    def test_timestamps_mapped(self):
        cb = CitationBuilder()
        result = cb.build([_make_doc(1, start_ts="3/1/2024", end_ts="3/1/2024 10:00")])
        assert result[0].start_timestamp == "3/1/2024"
        assert result[0].end_timestamp == "3/1/2024 10:00"

    def test_missing_source_chat_defaults_to_unknown(self):
        cb = CitationBuilder()
        doc = RetrievedDocument(
            document_id="no-chat",
            text="some text",
            metadata={},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="col",
            query="q",
        )
        result = cb.build([doc])
        assert result[0].source_chat == "Unknown"

    def test_missing_chunk_index_defaults_to_zero(self):
        cb = CitationBuilder()
        doc = RetrievedDocument(
            document_id="no-chunk",
            text="text",
            metadata={"source_chat": "Chat"},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="col",
            query="q",
        )
        result = cb.build([doc])
        assert result[0].chunk_index == 0

    def test_missing_timestamps_default_to_empty_string(self):
        cb = CitationBuilder()
        doc = RetrievedDocument(
            document_id="no-ts",
            text="text",
            metadata={"source_chat": "Chat", "chunk_index": 0},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="col",
            query="q",
        )
        result = cb.build([doc])
        assert result[0].start_timestamp == ""
        assert result[0].end_timestamp == ""

    def test_empty_list_raises_citation_error(self):
        cb = CitationBuilder()
        with pytest.raises(CitationError, match="empty"):
            cb.build([])

    def test_non_list_raises_citation_error(self):
        cb = CitationBuilder()
        with pytest.raises(CitationError):
            cb.build("not a list")  # type: ignore

    def test_invalid_item_in_list_raises_citation_error(self):
        cb = CitationBuilder()
        with pytest.raises(CitationError, match="RetrievedDocument"):
            cb.build([_make_doc(1), "bad item"])  # type: ignore

    def test_citations_are_citation_instances(self):
        cb = CitationBuilder()
        result = cb.build([_make_doc(1), _make_doc(2)])
        for c in result:
            assert isinstance(c, Citation)

    def test_negative_chunk_index_in_metadata_clamped_to_zero(self):
        cb = CitationBuilder()
        doc = RetrievedDocument(
            document_id="neg-chunk",
            text="text",
            metadata={"chunk_index": -5},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="col",
            query="q",
        )
        result = cb.build([doc])
        assert result[0].chunk_index == 0

    def test_invalid_chunk_index_type_defaults_to_zero(self):
        cb = CitationBuilder()
        doc = RetrievedDocument(
            document_id="bad-chunk",
            text="text",
            metadata={"chunk_index": "not-an-int"},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="col",
            query="q",
        )
        result = cb.build([doc])
        assert result[0].chunk_index == 0


# ===========================================================================
# 2. AnswerGenerator tests
# ===========================================================================

class TestAnswerGenerator:

    def _gen(self, **kw) -> AnswerGenerator:
        return AnswerGenerator(provider=FakeProvider(**kw))

    def test_returns_grounded_answer(self):
        ag = self._gen()
        docs = [_make_doc(1)]
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build(docs)
        result = ag.generate("What happened?", "Some context here.", citations)
        assert isinstance(result, GroundedAnswer)

    def test_answer_text_from_provider(self):
        ag = self._gen(text="Alice sent a PDF.")
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        result = ag.generate("q", "ctx", citations)
        assert result.answer == "Alice sent a PDF."

    def test_question_preserved(self):
        ag = self._gen()
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        result = ag.generate("My exact question", "context", citations)
        assert result.question == "My exact question"

    def test_citations_preserved(self):
        ag = self._gen()
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1), _make_doc(2)])
        result = ag.generate("q", "ctx", citations)
        assert result.citations == citations

    def test_provider_name_recorded(self):
        ag = AnswerGenerator(provider=FakeProvider(provider="my-provider"))
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        result = ag.generate("q", "ctx", citations)
        assert result.provider == "my-provider"

    def test_model_name_recorded(self):
        ag = AnswerGenerator(provider=FakeProvider(model="my-model"))
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        result = ag.generate("q", "ctx", citations)
        assert result.model == "my-model"

    def test_tokens_used_recorded(self):
        ag = self._gen(tokens=77)
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        result = ag.generate("q", "ctx", citations)
        assert result.tokens_used == 77

    def test_generation_time_positive(self):
        ag = self._gen()
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        result = ag.generate("q", "ctx", citations)
        assert result.generation_time >= 0.0

    def test_confidence_is_mean_of_scores(self):
        from app.generation.citation_builder import CitationBuilder
        docs = [_make_doc(1, score=0.8), _make_doc(2, score=0.6)]
        citations = CitationBuilder().build(docs)
        ag = self._gen()
        result = ag.generate("q", "ctx", citations)
        assert result.confidence == pytest.approx(0.7, abs=1e-4)

    def test_empty_provider_response_uses_fallback(self):
        ag = self._gen(text="")
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        result = ag.generate("q", "ctx", citations)
        assert "could not find" in result.answer.lower()

    def test_provider_failure_raises_answer_generation_error(self):
        ag = self._gen(should_fail=True)
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        with pytest.raises(AnswerGenerationError):
            ag.generate("q", "ctx", citations)

    def test_empty_question_raises(self):
        ag = self._gen()
        with pytest.raises(AnswerGenerationError, match="question"):
            ag.generate("", "ctx", ())

    def test_whitespace_question_raises(self):
        ag = self._gen()
        with pytest.raises(AnswerGenerationError, match="question"):
            ag.generate("   ", "ctx", ())

    def test_empty_context_raises(self):
        ag = self._gen()
        with pytest.raises(AnswerGenerationError, match="context"):
            ag.generate("question", "", ())

    def test_non_tuple_citations_raises(self):
        ag = self._gen()
        with pytest.raises(AnswerGenerationError, match="tuple"):
            ag.generate("q", "ctx", [])  # type: ignore — list, not tuple

    def test_provider_called_exactly_once(self):
        provider = FakeProvider()
        ag = AnswerGenerator(provider=provider)
        from app.generation.citation_builder import CitationBuilder
        citations = CitationBuilder().build([_make_doc(1)])
        ag.generate("q", "ctx", citations)
        assert provider.call_count == 1

    def test_wrong_provider_type_raises(self):
        with pytest.raises(AnswerGenerationError):
            AnswerGenerator(provider="not a provider")  # type: ignore

    def test_empty_citations_tuple_confidence_is_zero(self):
        ag = self._gen()
        result = ag.generate("q", "ctx", ())
        assert result.confidence == 0.0
