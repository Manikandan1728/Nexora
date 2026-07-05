"""
app/generation/answer_generator.py — Calls the LLM and wraps the response
in a GroundedAnswer.

WHY ANSWER GENERATION IS ISOLATED HERE
---------------------------------------
``AnswerGenerator`` is the only component in Phase 6 that crosses the
LLM boundary. Isolating it means:

  * The rest of the pipeline (ContextBuilder, PromptBuilder,
    CitationBuilder) is completely pure Python and never touches a
    network socket.
  * Tests for the pipeline can inject a fake ``ILLMProvider`` and run
    with zero network access in under a millisecond.
  * Swapping from OpenAI to Ollama to a future local model requires
    only changing the injected ``ILLMProvider`` — not this class.

WHY PromptBuilder.build_parts() IS USED INTERNALLY
---------------------------------------------------
``ILLMProvider.generate()`` accepts ``(system_prompt, user_prompt)``
as separate strings.  ``AnswerGenerator`` uses ``PromptBuilder.build_parts()``
to split the combined prompt string into those two parts, keeping the
split logic in one canonical place.

However, callers that have already assembled a full combined prompt string
can pass it directly — the generator also accepts a pre-built prompt to
avoid double-building.

CONFIDENCE CALCULATION
-----------------------
Confidence is the arithmetic mean of the similarity scores of the
citations.  It is a retrieval signal, not an LLM signal — high confidence
means the knowledge base strongly matched the query, not that the LLM
"feels confident".  This is intentional: LLM self-reported confidence is
notoriously unreliable for factual tasks.

GENERATION TIME
---------------
Wall-clock time is measured around the ``provider.generate()`` call only.
It does not include context building, prompt building, or citation building
— those are negligible and are timed separately by the pipeline.
"""

from __future__ import annotations

import logging
import time
from typing import Tuple

from models.answer import Citation, GroundedAnswer
from llm.interfaces import ILLMProvider
from app.generation.prompt_builder import PromptBuilder
from exceptions.exceptions import AnswerGenerationError

logger = logging.getLogger(__name__)

# Fallback answer when the provider returns empty text
_FALLBACK_ANSWER = (
    "I could not find that information in your knowledge base."
)


class AnswerGenerator:
    """
    Calls an ``ILLMProvider`` and wraps the response in a ``GroundedAnswer``.

    Parameters
    ----------
    provider : ILLMProvider
        The LLM backend to use for generation.  Injected so tests can
        supply a fake provider without touching real API credentials.

    Usage
    -----
    ::

        generator = AnswerGenerator(provider=fake_provider)
        answer = generator.generate(
            question="What files were shared?",
            context="[Document 1]\\nAlice: I sent the PDF.",
            citations=citations_tuple,
        )
        print(answer.answer)
    """

    def __init__(self, provider: ILLMProvider) -> None:
        if not isinstance(provider, ILLMProvider):
            raise AnswerGenerationError(
                f"AnswerGenerator requires an ILLMProvider, "
                f"got {type(provider).__name__}."
            )
        self._provider = provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        question: str,
        context: str,
        citations: tuple,
    ) -> GroundedAnswer:
        """
        Generate a grounded answer from a question, context, and citations.

        Steps:
        1. Validate inputs.
        2. Build (system_prompt, user_prompt) via PromptBuilder.
        3. Call provider.generate(system_prompt, user_prompt).
        4. Measure wall-clock generation time.
        5. Compute confidence from citation similarity scores.
        6. Return a frozen GroundedAnswer.

        Args:
            question:  The user's question.  Must be non-empty.
            context:   The context string from ContextBuilder.  Must be
                       non-empty.
            citations: Tuple of Citation objects from CitationBuilder.
                       May be empty (when no documents were retrieved),
                       but confidence will be 0.0 in that case.

        Returns:
            A frozen ``GroundedAnswer`` instance.

        Raises:
            AnswerGenerationError: If any input is invalid, if the prompt
                                   builder fails, or if the provider raises.
        """
        self._validate_inputs(question, context, citations)

        # Build the split prompt
        try:
            system_prompt, user_prompt = PromptBuilder.build_parts(
                question=question,
                context=context,
            )
        except Exception as exc:
            raise AnswerGenerationError(
                f"Prompt building failed before LLM call: {exc}"
            ) from exc

        # Log operational metadata — never log prompt content
        logger.info(
            "AnswerGenerator.generate: provider=%s  model=%s  "
            "citations=%d",
            self._provider.provider_name,
            self._provider.model_name,
            len(citations),
        )

        # Call the LLM and measure wall-clock time
        t0 = time.perf_counter()
        try:
            llm_response = self._provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            raise AnswerGenerationError(
                f"LLM provider '{self._provider.provider_name}' failed "
                f"during generation: {exc}"
            ) from exc
        generation_time = time.perf_counter() - t0

        # Use fallback text if the provider returned empty
        answer_text = llm_response.text.strip() or _FALLBACK_ANSWER

        # Compute confidence as mean similarity score of citations
        confidence = self._compute_confidence(citations)

        logger.info(
            "AnswerGenerator.generate: done  time=%.2fs  tokens=%d  "
            "confidence=%.4f",
            generation_time,
            llm_response.tokens_used,
            confidence,
        )

        return GroundedAnswer(
            question=question,
            answer=answer_text,
            citations=citations,
            confidence=confidence,
            provider=llm_response.provider,
            model=llm_response.model,
            generation_time=generation_time,
            tokens_used=llm_response.tokens_used,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence(citations: tuple) -> float:
        """
        Compute confidence as the mean similarity score across citations.

        Returns 0.0 when the citations tuple is empty.
        """
        if not citations:
            return 0.0
        scores = [c.similarity_score for c in citations if isinstance(c, Citation)]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    @staticmethod
    def _validate_inputs(question: str, context: str, citations: tuple) -> None:
        """
        Validate the three inputs before building the prompt.

        Raises:
            AnswerGenerationError: On any contract violation.
        """
        if not isinstance(question, str) or not question.strip():
            raise AnswerGenerationError(
                "question must be a non-empty string."
            )
        if not isinstance(context, str) or not context.strip():
            raise AnswerGenerationError(
                "context must be a non-empty string."
            )
        if not isinstance(citations, tuple):
            raise AnswerGenerationError(
                f"citations must be a tuple, got {type(citations).__name__}."
            )
