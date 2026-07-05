"""
app/generation/phase6_pipeline.py — Phase 6 orchestrator.

WHY THIS MODULE EXISTS
-----------------------
Each Phase 6 sub-component has exactly one responsibility:

  ContextBuilder   — List[RetrievedDocument] → context string
  PromptBuilder    — context + question → prompt parts
  CitationBuilder  — List[RetrievedDocument] → tuple[Citation, ...]
  AnswerGenerator  — prompt + provider → GroundedAnswer

``Phase6Pipeline`` wires them together behind a single entry point:

    answer = Phase6Pipeline(provider=provider).run(
        question="What did Alice share?",
        retrieved_documents=docs,
    )

WHAT THIS PIPELINE DOES NOT DO
--------------------------------
  * It does not perform retrieval (that is Phase 5).
  * It does not search ChromaDB.
  * It does not generate embeddings.
  * It does not modify retrieved documents.
  * It does not implement a REST API or UI.
  * It does not call OpenAI or Ollama directly — it only calls
    ``ILLMProvider.generate()``.

DEPENDENCY INJECTION
---------------------
All five collaborators are constructor-injectable:

  * ``provider``   — the LLM backend (test: inject a fake provider)
  * ``config``     — controls context budget (test: inject small budget)
  * ``context_builder``  — override for specialised formatting
  * ``citation_builder`` — override for specialised citation format
  * ``answer_generator`` — override to wrap generation differently

This satisfies the Dependency Inversion Principle: the pipeline depends
on abstractions, not on concrete implementations.

EMPTY RETRIEVED DOCUMENTS
--------------------------
When ``retrieved_documents`` is empty, the pipeline raises
``ContextBuildError`` rather than passing an empty context to the LLM.
An empty context would produce an ungrounded answer — exactly what RAG
is designed to prevent.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from models.retrieved_document import RetrievedDocument
from models.answer import GroundedAnswer
from config.llm_config import LLMConfig
from llm.interfaces import ILLMProvider
from app.generation.context_builder import ContextBuilder
from app.generation.citation_builder import CitationBuilder
from app.generation.answer_generator import AnswerGenerator
from exceptions.exceptions import (
    ContextBuildError,
    CitationError,
    AnswerGenerationError,
)

logger = logging.getLogger(__name__)


class Phase6Pipeline:
    """
    Orchestrates the full Phase 6 grounded-answer generation flow.

    Parameters
    ----------
    provider : ILLMProvider
        The LLM backend.  Injected to allow test mocking without hitting
        real APIs.

    config : LLMConfig, optional
        Configuration controlling context token budget.  Defaults to
        a standard Ollama config.

    context_builder : ContextBuilder, optional
        Override for specialised context formatting.  Defaults to
        ``ContextBuilder(config)``.

    citation_builder : CitationBuilder, optional
        Override for specialised citation handling.  Defaults to
        ``CitationBuilder()``.

    answer_generator : AnswerGenerator, optional
        Override for specialised answer wrapping.  Defaults to
        ``AnswerGenerator(provider)``.

    Example
    -------
    ::

        from llm.ollama_provider import OllamaProvider
        from config.llm_config import LLMConfig
        from app.generation.phase6_pipeline import Phase6Pipeline

        config   = LLMConfig(provider="ollama", model="llama3")
        provider = OllamaProvider(config)
        pipeline = Phase6Pipeline(provider=provider, config=config)

        answer = pipeline.run(
            question="What files did Alice share?",
            retrieved_documents=results,
        )
        print(answer.answer)
        print(answer.citations)
    """

    def __init__(
        self,
        provider: ILLMProvider,
        config: Optional[LLMConfig] = None,
        context_builder: Optional[ContextBuilder] = None,
        citation_builder: Optional[CitationBuilder] = None,
        answer_generator: Optional[AnswerGenerator] = None,
    ) -> None:
        if not isinstance(provider, ILLMProvider):
            raise AnswerGenerationError(
                f"Phase6Pipeline requires an ILLMProvider, "
                f"got {type(provider).__name__}."
            )

        self._provider = provider
        self._config = config or LLMConfig(provider="ollama")
        self._context_builder = context_builder or ContextBuilder(self._config)
        self._citation_builder = citation_builder or CitationBuilder()
        self._answer_generator = answer_generator or AnswerGenerator(provider)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        question: str,
        retrieved_documents: List[RetrievedDocument],
    ) -> GroundedAnswer:
        """
        Execute the full Phase 6 generation pipeline.

        Steps:
        1. Validate inputs.
        2. Build the context string from retrieved documents.
        3. Build citations from the same retrieved documents.
        4. Call the answer generator (which calls the LLM provider).
        5. Return the GroundedAnswer.

        Args:
            question:            The user's question.  Must be non-empty.
            retrieved_documents: Ranked ``List[RetrievedDocument]`` from
                                 Phase 5.  Must be non-empty.

        Returns:
            A frozen ``GroundedAnswer`` with answer text, citations,
            confidence score, provider/model info, and token usage.

        Raises:
            ContextBuildError:    If documents are empty or invalid.
            CitationError:        If citation building fails.
            AnswerGenerationError: If the LLM call fails.
        """
        if not isinstance(question, str) or not question.strip():
            raise AnswerGenerationError(
                "Phase6Pipeline.run() requires a non-empty question string."
            )
        if not isinstance(retrieved_documents, list) or len(retrieved_documents) == 0:
            raise ContextBuildError(
                "Phase6Pipeline.run() requires a non-empty list of "
                "RetrievedDocuments.  Run Phase 5 retrieval first."
            )

        wall_start = time.perf_counter()

        logger.info(
            "Phase6Pipeline.run: question=%r  documents=%d  "
            "provider=%s  model=%s",
            question[:80],
            len(retrieved_documents),
            self._provider.provider_name,
            self._provider.model_name,
        )

        # ── Stage 1: Build context ────────────────────────────────────
        context = self._context_builder.build(retrieved_documents)
        logger.debug(
            "Phase6Pipeline: context built (%d chars).", len(context)
        )

        # ── Stage 2: Build citations ──────────────────────────────────
        citations = self._citation_builder.build(retrieved_documents)
        logger.debug(
            "Phase6Pipeline: %d citation(s) built.", len(citations)
        )

        # ── Stage 3: Generate answer ──────────────────────────────────
        answer = self._answer_generator.generate(
            question=question,
            context=context,
            citations=citations,
        )

        elapsed = time.perf_counter() - wall_start
        logger.info(
            "Phase6Pipeline.run: complete  total_time=%.2fs  "
            "gen_time=%.2fs  tokens=%d  confidence=%.4f",
            elapsed,
            answer.generation_time,
            answer.tokens_used,
            answer.confidence,
        )

        return answer
