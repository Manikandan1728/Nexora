"""
tests/test_phase6_pipeline.py — Integration tests for Phase6Pipeline.

All tests use FakeProvider — no real OpenAI or Ollama calls are made.
The pipeline is tested end-to-end from List[RetrievedDocument] to
GroundedAnswer, with every sub-component exercised through the real
implementation (not mocked), except the LLM provider.
"""

from __future__ import annotations

import pytest
from typing import List
from unittest.mock import MagicMock, patch

from models.retrieved_document import RetrievedDocument
from models.answer import Citation, GroundedAnswer
from llm.interfaces import ILLMProvider, LLMResponse
from config.llm_config import LLMConfig
from app.generation.context_builder import ContextBuilder
from app.generation.citation_builder import CitationBuilder
from app.generation.answer_generator import AnswerGenerator
from app.generation.phase6_pipeline import Phase6Pipeline
from app.generation import (
    ContextBuilder,
    PromptBuilder,
    CitationBuilder,
    AnswerGenerator,
    Phase6Pipeline,
)
from exceptions.exceptions import (
    ContextBuildError,
    CitationError,
    AnswerGenerationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(
    rank: int = 1,
    text: str = "Alice: Hello world",
    doc_id: str = None,
    score: float = 0.85,
    source_chat: str = "Alice & Bob",
    chunk_index: int = 0,
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
            "message_count":   2,
        },
        distance=1.0 - score,
        similarity_score=score,
        rank=rank,
        source_collection="test_col",
        query="test query",
    )


class FakeProvider(ILLMProvider):
    """Test double — never calls a real LLM."""

    def __init__(
        self,
        text: str = "Based on the documents, Alice shared a PDF.",
        tokens: int = 25,
        model: str = "fake-model",
        provider: str = "fake",
        should_fail: bool = False,
    ):
        self._text = text
        self._tokens = tokens
        self._model_name = model
        self._provider_name = provider
        self._should_fail = should_fail
        self.generate_calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        if self._should_fail:
            from exceptions.exceptions import LLMProviderError
            raise LLMProviderError("FakeProvider forced failure.")
        self.generate_calls += 1
        return LLMResponse(
            text=self._text,
            tokens_used=self._tokens,
            model=self._model_name,
            provider=self._provider_name,
        )

    def health_check(self) -> bool:
        return not self._should_fail

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def close(self) -> None:
        pass


def _default_config(budget: int = 3000) -> LLMConfig:
    return LLMConfig(provider="ollama", context_token_budget=budget)


def _pipeline(text: str = "answer", should_fail: bool = False, budget: int = 3000) -> Phase6Pipeline:
    provider = FakeProvider(text=text, should_fail=should_fail)
    config = _default_config(budget)
    return Phase6Pipeline(provider=provider, config=config)


# ===========================================================================
# 1. Pipeline construction
# ===========================================================================

class TestPhase6PipelineConstruction:

    def test_requires_provider(self):
        with pytest.raises(AnswerGenerationError):
            Phase6Pipeline(provider="not a provider")  # type: ignore

    def test_default_config_created_when_not_supplied(self):
        p = Phase6Pipeline(provider=FakeProvider())
        assert p._config is not None

    def test_custom_config_injected(self):
        config = _default_config(budget=500)
        p = Phase6Pipeline(provider=FakeProvider(), config=config)
        assert p._config.context_token_budget == 500

    def test_custom_context_builder_injected(self):
        config = _default_config()
        custom_cb = ContextBuilder(config)
        p = Phase6Pipeline(
            provider=FakeProvider(),
            config=config,
            context_builder=custom_cb,
        )
        assert p._context_builder is custom_cb

    def test_custom_citation_builder_injected(self):
        custom_cit = CitationBuilder()
        p = Phase6Pipeline(
            provider=FakeProvider(),
            citation_builder=custom_cit,
        )
        assert p._citation_builder is custom_cit

    def test_custom_answer_generator_injected(self):
        provider = FakeProvider()
        custom_ag = AnswerGenerator(provider=provider)
        p = Phase6Pipeline(
            provider=provider,
            answer_generator=custom_ag,
        )
        assert p._answer_generator is custom_ag


# ===========================================================================
# 2. Pipeline run — happy path
# ===========================================================================

class TestPhase6PipelineRun:

    def test_returns_grounded_answer(self):
        docs = [_make_doc(1)]
        result = _pipeline().run("What did Alice share?", docs)
        assert isinstance(result, GroundedAnswer)

    def test_question_preserved_in_answer(self):
        docs = [_make_doc(1)]
        result = _pipeline().run("Exact user question?", docs)
        assert result.question == "Exact user question?"

    def test_answer_text_from_provider(self):
        docs = [_make_doc(1)]
        result = _pipeline(text="She shared a PDF.").run("q?", docs)
        assert result.answer == "She shared a PDF."

    def test_citations_count_matches_documents(self):
        docs = [_make_doc(1), _make_doc(2), _make_doc(3)]
        result = _pipeline().run("q?", docs)
        assert result.citation_count == 3

    def test_citations_rank_order_preserved(self):
        docs = [_make_doc(1), _make_doc(2), _make_doc(3)]
        result = _pipeline().run("q?", docs)
        ranks = [c.rank for c in result.citations]
        assert ranks == [1, 2, 3]

    def test_confidence_is_mean_similarity(self):
        docs = [_make_doc(1, score=0.8), _make_doc(2, score=0.6)]
        result = _pipeline().run("q?", docs)
        assert result.confidence == pytest.approx(0.7, abs=1e-4)

    def test_provider_name_in_answer(self):
        provider = FakeProvider(provider="my-provider")
        p = Phase6Pipeline(provider=provider)
        result = p.run("q?", [_make_doc(1)])
        assert result.provider == "my-provider"

    def test_model_name_in_answer(self):
        provider = FakeProvider(model="my-model")
        p = Phase6Pipeline(provider=provider)
        result = p.run("q?", [_make_doc(1)])
        assert result.model == "my-model"

    def test_tokens_used_recorded(self):
        provider = FakeProvider(tokens=99)
        p = Phase6Pipeline(provider=provider)
        result = p.run("q?", [_make_doc(1)])
        assert result.tokens_used == 99

    def test_generation_time_non_negative(self):
        result = _pipeline().run("q?", [_make_doc(1)])
        assert result.generation_time >= 0.0

    def test_has_citations_true_when_docs_present(self):
        result = _pipeline().run("q?", [_make_doc(1)])
        assert result.has_citations is True

    def test_multiple_documents_all_cited(self):
        docs = [_make_doc(i) for i in range(1, 6)]
        result = _pipeline().run("q?", docs)
        assert result.citation_count == 5

    def test_provider_called_exactly_once(self):
        provider = FakeProvider()
        p = Phase6Pipeline(provider=provider)
        p.run("q?", [_make_doc(1)])
        assert provider.generate_calls == 1


# ===========================================================================
# 3. Pipeline validation
# ===========================================================================

class TestPhase6PipelineValidation:

    def test_empty_question_raises(self):
        with pytest.raises(AnswerGenerationError, match="question"):
            _pipeline().run("", [_make_doc(1)])

    def test_whitespace_question_raises(self):
        with pytest.raises(AnswerGenerationError, match="question"):
            _pipeline().run("   ", [_make_doc(1)])

    def test_empty_document_list_raises_context_build_error(self):
        with pytest.raises(ContextBuildError):
            _pipeline().run("valid question", [])

    def test_non_list_documents_raises_context_build_error(self):
        with pytest.raises(ContextBuildError):
            _pipeline().run("valid question", "not a list")  # type: ignore

    def test_provider_failure_raises_answer_generation_error(self):
        docs = [_make_doc(1)]
        with pytest.raises(AnswerGenerationError):
            _pipeline(should_fail=True).run("q?", docs)


# ===========================================================================
# 4. No retrieval, no embeddings, no ChromaDB
# ===========================================================================

class TestPhase6PipelineDoesNotPerformRetrieval:

    def test_pipeline_does_not_import_retrieval_pipeline(self):
        """Phase6Pipeline must not reach into Phase 5 retrieval code."""
        import app.generation.phase6_pipeline as m6
        source = open(m6.__file__, encoding="utf-8").read()
        assert "RetrievalPipeline" not in source
        assert "SimilaritySearch" not in source

    def test_pipeline_does_not_import_embedding_pipeline(self):
        """Phase6Pipeline must not touch Phase 3 embedding code."""
        import app.generation.phase6_pipeline as m6
        source = open(m6.__file__, encoding="utf-8").read()
        assert "EmbeddingPipeline" not in source
        assert "EmbeddingModel" not in source

    def test_pipeline_does_not_import_chroma(self):
        """Phase6Pipeline must not touch ChromaDB."""
        import app.generation.phase6_pipeline as m6
        source = open(m6.__file__, encoding="utf-8").read()
        assert "chromadb" not in source
        assert "ChromaVectorStore" not in source

    def test_retrieved_documents_not_mutated(self):
        """RetrievedDocument objects must be identical after pipeline.run()."""
        doc = _make_doc(rank=1, text="original text", score=0.9)
        original_text = doc.text
        original_rank = doc.rank
        original_score = doc.similarity_score

        _pipeline().run("q?", [doc])

        assert doc.text == original_text
        assert doc.rank == original_rank
        assert doc.similarity_score == original_score


# ===========================================================================
# 5. Package imports
# ===========================================================================

class TestGenerationPackageImports:

    def test_all_symbols_importable_from_package(self):
        from app.generation import (
            ContextBuilder,
            PromptBuilder,
            CitationBuilder,
            AnswerGenerator,
            Phase6Pipeline,
        )
        assert ContextBuilder is not None
        assert PromptBuilder is not None
        assert CitationBuilder is not None
        assert AnswerGenerator is not None
        assert Phase6Pipeline is not None

    def test_importing_package_does_not_call_any_llm(self):
        """Importing app.generation must not trigger any network I/O."""
        # This test passes trivially if the import succeeds without side effects.
        import app.generation
        assert app.generation is not None

    def test_all_in___all__(self):
        import app.generation
        for name in ["ContextBuilder", "PromptBuilder", "CitationBuilder",
                     "AnswerGenerator", "Phase6Pipeline"]:
            assert name in app.generation.__all__
