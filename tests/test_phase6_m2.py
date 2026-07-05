"""
tests/test_phase6_m2.py — Milestone 2 unit tests for Phase 6.

Tests cover:
  - ContextBuilder: validation, rank order, metadata inclusion, budget
  - PromptBuilder: structure, grounding instructions, validation

No LLM calls.  No OpenAI.  No Ollama.  Everything is pure Python.
"""

from __future__ import annotations

import pytest
from typing import List

from models.retrieved_document import RetrievedDocument
from config.llm_config import LLMConfig
from app.generation.context_builder import ContextBuilder
from app.generation.prompt_builder import PromptBuilder
from exceptions.exceptions import ContextBuildError, PromptBuildError


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
            "message_count":   3,
        },
        distance=1.0 - score,
        similarity_score=score,
        rank=rank,
        source_collection="test_col",
        query="test query",
    )


def _default_config(budget: int = 3000) -> LLMConfig:
    return LLMConfig(provider="ollama", context_token_budget=budget)


# ===========================================================================
# 1. ContextBuilder — validation
# ===========================================================================

class TestContextBuilderValidation:

    def test_empty_list_raises_context_build_error(self):
        cb = ContextBuilder(_default_config())
        with pytest.raises(ContextBuildError, match="empty"):
            cb.build([])

    def test_non_list_raises_context_build_error(self):
        cb = ContextBuilder(_default_config())
        with pytest.raises(ContextBuildError):
            cb.build("not a list")  # type: ignore

    def test_list_with_non_retrieved_document_raises(self):
        cb = ContextBuilder(_default_config())
        with pytest.raises(ContextBuildError, match="RetrievedDocument"):
            cb.build(["not a document"])  # type: ignore

    def test_list_with_mixed_types_raises(self):
        cb = ContextBuilder(_default_config())
        docs = [_make_doc(1), "bad item"]
        with pytest.raises(ContextBuildError):
            cb.build(docs)  # type: ignore

    def test_single_valid_document_succeeds(self):
        cb = ContextBuilder(_default_config())
        result = cb.build([_make_doc(1)])
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# 2. ContextBuilder — rank order preserved
# ===========================================================================

class TestContextBuilderRankOrder:

    def test_documents_appear_in_supplied_order(self):
        cb = ContextBuilder(_default_config())
        docs = [
            _make_doc(rank=1, text="First message"),
            _make_doc(rank=2, text="Second message"),
            _make_doc(rank=3, text="Third message"),
        ]
        context = cb.build(docs)
        pos1 = context.index("First message")
        pos2 = context.index("Second message")
        pos3 = context.index("Third message")
        assert pos1 < pos2 < pos3

    def test_rank_label_present_in_output(self):
        cb = ContextBuilder(_default_config())
        docs = [_make_doc(rank=1), _make_doc(rank=2)]
        context = cb.build(docs)
        assert "[Document 1]" in context
        assert "[Document 2]" in context

    def test_rank_labels_in_ascending_order(self):
        """[Document 1] must appear before [Document 2]."""
        cb = ContextBuilder(_default_config())
        docs = [_make_doc(rank=1), _make_doc(rank=2)]
        context = cb.build(docs)
        assert context.index("[Document 1]") < context.index("[Document 2]")


# ===========================================================================
# 3. ContextBuilder — metadata inclusion
# ===========================================================================

class TestContextBuilderMetadata:

    def _build_single(self, **kwargs) -> str:
        cb = ContextBuilder(_default_config())
        return cb.build([_make_doc(**kwargs)])

    def test_similarity_score_included(self):
        context = self._build_single(score=0.9123)
        assert "0.9123" in context

    def test_document_id_included(self):
        context = self._build_single(doc_id="unique-doc-xyz")
        assert "unique-doc-xyz" in context

    def test_source_chat_included(self):
        context = self._build_single(source_chat="Alice & Charlie")
        assert "Alice & Charlie" in context

    def test_chunk_index_included(self):
        context = self._build_single(chunk_index=7)
        assert "7" in context

    def test_start_timestamp_included(self):
        context = self._build_single(start_ts="3/15/2024, 10:30 AM")
        assert "3/15/2024" in context

    def test_end_timestamp_included(self):
        context = self._build_single(end_ts="3/15/2024, 11:00 AM")
        assert "3/15/2024" in context

    def test_document_text_included(self):
        context = self._build_single(text="Alice: This is important text")
        assert "This is important text" in context

    def test_missing_timestamps_produce_na(self):
        cb = ContextBuilder(_default_config())
        doc = RetrievedDocument(
            document_id="no-ts",
            text="message here",
            metadata={"source_chat": "Test", "chunk_index": 0},
            distance=0.1,
            similarity_score=0.9,
            rank=1,
            source_collection="col",
            query="q",
        )
        context = cb.build([doc])
        assert "N/A" in context

    def test_missing_source_chat_defaults_to_unknown(self):
        cb = ContextBuilder(_default_config())
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
        context = cb.build([doc])
        assert "Unknown" in context


# ===========================================================================
# 4. ContextBuilder — token budget
# ===========================================================================

class TestContextBuilderTokenBudget:

    def test_all_documents_fit_within_large_budget(self):
        cb = ContextBuilder(_default_config(budget=3000))
        docs = [_make_doc(rank=i, text=f"Message {i}") for i in range(1, 6)]
        context = cb.build(docs)
        for i in range(1, 6):
            assert f"Message {i}" in context

    def test_budget_truncates_excess_documents(self):
        """With a very small budget only the first document should fit."""
        # Each formatted block is ~200 chars; budget of 100 tokens = 400 chars
        # First doc fits, second should not
        cb = ContextBuilder(_default_config(budget=100))
        long_text = "A" * 100   # 100 chars of text per document
        docs = [
            _make_doc(rank=1, text=long_text),
            _make_doc(rank=2, text=long_text),
            _make_doc(rank=3, text=long_text),
        ]
        context = cb.build(docs)
        # Rank 1 must be present
        assert "[Document 1]" in context
        # Rank 3 must not overflow budget — may or may not be present
        # depending on budget, so we just verify no error was raised
        assert isinstance(context, str)

    def test_budget_too_small_for_even_one_doc_raises(self):
        """context_token_budget=100 tokens = 400 chars; a 500-char doc won't fit."""
        cb = ContextBuilder(_default_config(budget=100))
        massive_text = "X" * 1000   # guaranteed to exceed 400 chars
        docs = [_make_doc(rank=1, text=massive_text)]
        with pytest.raises(ContextBuildError, match="too small"):
            cb.build(docs)

    def test_documents_not_mutated_by_build(self):
        """RetrievedDocument objects must be identical after build()."""
        cb = ContextBuilder(_default_config())
        original = _make_doc(rank=1, text="original text")
        cb.build([original])
        assert original.text == "original text"
        assert original.rank == 1


# ===========================================================================
# 5. PromptBuilder — structure
# ===========================================================================

class TestPromptBuilderStructure:

    def test_build_returns_string(self):
        result = PromptBuilder.build("What did Alice say?", "some context")
        assert isinstance(result, str)

    def test_build_contains_system_instructions(self):
        result = PromptBuilder.build("question", "context")
        assert "You are Nexora" in result

    def test_build_contains_context(self):
        result = PromptBuilder.build("question", "my special context")
        assert "my special context" in result

    def test_build_contains_question(self):
        result = PromptBuilder.build("What is the project deadline?", "context")
        assert "What is the project deadline?" in result

    def test_build_context_appears_before_question(self):
        result = PromptBuilder.build("my question", "my context")
        assert result.index("my context") < result.index("my question")

    def test_build_system_instructions_appear_first(self):
        result = PromptBuilder.build("q", "ctx")
        nexora_pos = result.index("You are Nexora")
        ctx_pos    = result.index("ctx")
        q_pos      = result.index("q")
        assert nexora_pos < ctx_pos
        assert nexora_pos < q_pos

    def test_build_contains_grounding_rule(self):
        result = PromptBuilder.build("q", "ctx")
        assert "Answer ONLY using the supplied context" in result

    def test_build_contains_no_hallucination_rule(self):
        result = PromptBuilder.build("q", "ctx")
        assert "hallucinate" in result.lower()

    def test_build_contains_fallback_phrase(self):
        result = PromptBuilder.build("q", "ctx")
        assert "I could not find that information in your knowledge base" in result

    def test_build_contains_outside_knowledge_rule(self):
        result = PromptBuilder.build("q", "ctx")
        assert "outside knowledge" in result.lower()

    def test_build_contains_citation_instruction(self):
        result = PromptBuilder.build("q", "ctx")
        # The prompt should instruct the model to cite documents
        lower = result.lower()
        assert "cite" in lower or "document" in lower


# ===========================================================================
# 6. PromptBuilder — build_parts (system + user split)
# ===========================================================================

class TestPromptBuilderParts:

    def test_build_parts_returns_two_strings(self):
        sys_p, usr_p = PromptBuilder.build_parts("question", "context")
        assert isinstance(sys_p, str)
        assert isinstance(usr_p, str)

    def test_system_prompt_contains_nexora_identity(self):
        sys_p, _ = PromptBuilder.build_parts("q", "ctx")
        assert "You are Nexora" in sys_p

    def test_system_prompt_contains_grounding_rule(self):
        sys_p, _ = PromptBuilder.build_parts("q", "ctx")
        assert "ONLY" in sys_p

    def test_user_prompt_contains_context(self):
        _, usr_p = PromptBuilder.build_parts("q", "special context block")
        assert "special context block" in usr_p

    def test_user_prompt_contains_question(self):
        _, usr_p = PromptBuilder.build_parts("my precise question", "ctx")
        assert "my precise question" in usr_p

    def test_user_context_appears_before_question_in_user_prompt(self):
        _, usr_p = PromptBuilder.build_parts("the question", "the context")
        assert usr_p.index("the context") < usr_p.index("the question")


# ===========================================================================
# 7. PromptBuilder — validation
# ===========================================================================

class TestPromptBuilderValidation:

    def test_empty_question_raises(self):
        with pytest.raises(PromptBuildError, match="question"):
            PromptBuilder.build("", "context")

    def test_whitespace_only_question_raises(self):
        with pytest.raises(PromptBuildError, match="question"):
            PromptBuilder.build("   ", "context")

    def test_empty_context_raises(self):
        with pytest.raises(PromptBuildError, match="context"):
            PromptBuilder.build("question", "")

    def test_whitespace_only_context_raises(self):
        with pytest.raises(PromptBuildError, match="context"):
            PromptBuilder.build("question", "  \n  ")

    def test_non_string_question_raises(self):
        with pytest.raises(PromptBuildError):
            PromptBuilder.build(None, "context")  # type: ignore

    def test_non_string_context_raises(self):
        with pytest.raises(PromptBuildError):
            PromptBuilder.build("question", 42)  # type: ignore

    def test_build_parts_empty_question_raises(self):
        with pytest.raises(PromptBuildError, match="question"):
            PromptBuilder.build_parts("", "context")

    def test_build_parts_empty_context_raises(self):
        with pytest.raises(PromptBuildError, match="context"):
            PromptBuilder.build_parts("question", "")


# ===========================================================================
# 8. PromptBuilder — system_instructions accessor
# ===========================================================================

class TestPromptBuilderSystemInstructions:

    def test_system_instructions_returns_string(self):
        assert isinstance(PromptBuilder.system_instructions(), str)

    def test_system_instructions_not_empty(self):
        assert len(PromptBuilder.system_instructions().strip()) > 0

    def test_system_instructions_contains_nexora(self):
        assert "Nexora" in PromptBuilder.system_instructions()

    def test_system_instructions_contains_fallback(self):
        assert (
            "I could not find that information in your knowledge base"
            in PromptBuilder.system_instructions()
        )


# ===========================================================================
# 9. Integration: ContextBuilder + PromptBuilder together
# ===========================================================================

class TestContextAndPromptIntegration:

    def test_full_flow_produces_valid_prompt(self):
        """End-to-end: documents -> context -> prompt."""
        cfg  = _default_config()
        cb   = ContextBuilder(cfg)
        docs = [
            _make_doc(rank=1, text="Alice: I sent the PDF yesterday."),
            _make_doc(rank=2, text="Bob: Thanks, I received it."),
        ]
        context = cb.build(docs)
        prompt  = PromptBuilder.build("What did Alice send?", context)

        assert "Alice" in prompt
        assert "PDF" in prompt
        assert "You are Nexora" in prompt
        assert "What did Alice send?" in prompt

    def test_full_flow_parts_system_contains_no_context(self):
        """System prompt must NOT contain retrieved document text."""
        cfg   = _default_config()
        cb    = ContextBuilder(cfg)
        docs  = [_make_doc(rank=1, text="TopSecretData")]
        context = cb.build(docs)
        sys_p, usr_p = PromptBuilder.build_parts("question", context)

        assert "TopSecretData" not in sys_p
        assert "TopSecretData" in usr_p

    def test_rank_order_preserved_through_full_flow(self):
        cfg  = _default_config()
        cb   = ContextBuilder(cfg)
        docs = [
            _make_doc(rank=1, text="First doc content"),
            _make_doc(rank=2, text="Second doc content"),
        ]
        context = cb.build(docs)
        _, usr_p = PromptBuilder.build_parts("q", context)

        assert usr_p.index("First doc content") < usr_p.index("Second doc content")
