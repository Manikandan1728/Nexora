"""
app/generation/prompt_builder.py — Assembles the grounded LLM prompt.

WHY PROMPTS REQUIRE RETRIEVED CONTEXT
--------------------------------------
Language models trained on internet text will answer questions from their
parametric memory — knowledge baked in during training. For a personal
knowledge base over private Telegram conversations, that parametric
knowledge is useless and actively harmful: the model would invent plausible-
sounding answers based on patterns in its training data, not on the user's
actual conversation history.

Retrieval-Augmented Generation (RAG) solves this by injecting the retrieved
text directly into the prompt, then instructing the model to answer ONLY
from that text. This constrains the model's output to facts that actually
appear in the knowledge base.

WHY HALLUCINATIONS OCCUR AND HOW GROUNDING PREVENTS THEM
----------------------------------------------------------
Hallucination happens when a model fills gaps in its knowledge with
statistically likely but factually wrong text. The model has no way to
distinguish "I know this" from "I am guessing". Explicit grounding
instructions in the system prompt + a retrieved context that contains the
answer eliminates the gap — the model no longer needs to guess.

WHY PROMPT STRUCTURE MATTERS
-----------------------------
The prompt is divided into four sections in a deliberate order:

  1. SYSTEM INSTRUCTIONS — loaded first so the model internalises its
     role and constraints before reading any content.
  2. CONTEXT — the retrieved documents. Placed before the question so
     the model has the evidence in working memory when it reads the ask.
  3. QUESTION — the user's query, clearly delimited so the model knows
     exactly what to answer.
  4. RESPONSE RULES — final reminders placed last so they are closest
     to the generation point in the attention window.

WHY CITATIONS ARE REQUIRED
---------------------------
An answer without provenance cannot be verified. If the model says
"You shared a PDF on March 3rd", the user needs to know which document
chunk supports that claim so they can cross-check it. Citations turn a
plausible completion into an auditable, trustworthy answer.
"""

from __future__ import annotations

import logging
from typing import Optional

from exceptions.exceptions import PromptBuildError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixed system instructions — grounding and safety rules
# ---------------------------------------------------------------------------
_SYSTEM_INSTRUCTIONS: str = """You are Nexora, a personal knowledge assistant.

Your ONLY task is to answer the user's question using the retrieved documents provided below.

Rules you must follow without exception:
- Answer ONLY using the supplied context. Do not use outside knowledge.
- Never invent, guess, or extrapolate information that is not present in the context.
- Do not hallucinate names, dates, files, or events.
- If the answer cannot be found in the context, reply exactly:
  "I could not find that information in your knowledge base."
- Always base your answer on the retrieved documents.
- When you use information from a document, refer to it by its [Document N] label.
- Be concise and factual."""

# Section delimiters — clear visual boundaries help the LLM segment the prompt
_CONTEXT_HEADER:   str = "=== RETRIEVED CONTEXT ==="
_CONTEXT_FOOTER:   str = "=== END OF CONTEXT ==="
_QUESTION_HEADER:  str = "=== USER QUESTION ==="
_RULES_HEADER:     str = "=== RESPONSE RULES ==="

# Final reminders placed immediately before generation
_RESPONSE_RULES: str = (
    "- Answer in clear, natural language.\n"
    "- Cite the [Document N] labels where relevant.\n"
    "- If no document contains the answer, say exactly:\n"
    "  \"I could not find that information in your knowledge base.\"\n"
    "- Do not add information beyond what the context contains."
)


class PromptBuilder:
    """
    Assembles the full LLM prompt from a context string and a question.

    The prompt has this structure::

        [SYSTEM INSTRUCTIONS]

        [CONTEXT HEADER]
        <context string from ContextBuilder>
        [CONTEXT FOOTER]

        [QUESTION HEADER]
        <user question>

        [RESPONSE RULES]

    This class has no state and all methods are static.  It exists as a
    class (not a module-level function) for consistency with the rest of
    the generation package and to enable subclassing for specialised
    prompt variants in future milestones.

    Responsibilities
    ----------------
    * Validate that neither the question nor the context is empty.
    * Assemble the four sections in the correct order.
    * Return the complete prompt as a single string.
    * Raise ``PromptBuildError`` on invalid input — never return a
      partially built prompt.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def build(question: str, context: str) -> str:
        """
        Build and return the complete grounded prompt string.

        Args:
            question: The user's question (post-preprocessing from Phase 5).
                      Must be a non-empty string.
            context:  The context string produced by ``ContextBuilder.build()``.
                      Must be a non-empty string.

        Returns:
            Single multi-line string ready to be split into
            ``system_prompt`` + ``user_prompt`` by the caller, or passed
            directly to a provider that accepts a combined prompt.

        Raises:
            PromptBuildError: If ``question`` or ``context`` is empty,
                              not a string, or whitespace-only.
        """
        PromptBuilder._validate(question, context)

        parts = [
            _SYSTEM_INSTRUCTIONS,
            "",
            _CONTEXT_HEADER,
            context.strip(),
            _CONTEXT_FOOTER,
            "",
            _QUESTION_HEADER,
            question.strip(),
            "",
            _RULES_HEADER,
            _RESPONSE_RULES,
        ]

        prompt = "\n".join(parts)

        logger.debug(
            "PromptBuilder.build: prompt assembled "
            "(%d chars, question=%r).",
            len(prompt),
            question[:60],
        )
        return prompt

    @staticmethod
    def build_parts(question: str, context: str) -> tuple:
        """
        Build the prompt and return it split into ``(system_prompt, user_prompt)``.

        This matches the ``ILLMProvider.generate(system_prompt, user_prompt)``
        interface directly, so the pipeline does not need to split the
        combined prompt string itself.

        The system prompt carries the grounding instructions.
        The user prompt carries the context + question + response rules.

        Args:
            question: The user's question.
            context:  The context string from ``ContextBuilder``.

        Returns:
            ``(system_prompt: str, user_prompt: str)`` tuple.

        Raises:
            PromptBuildError: Same conditions as ``build()``.
        """
        PromptBuilder._validate(question, context)

        user_parts = [
            _CONTEXT_HEADER,
            context.strip(),
            _CONTEXT_FOOTER,
            "",
            _QUESTION_HEADER,
            question.strip(),
            "",
            _RULES_HEADER,
            _RESPONSE_RULES,
        ]

        system_prompt = _SYSTEM_INSTRUCTIONS
        user_prompt   = "\n".join(user_parts)

        logger.debug(
            "PromptBuilder.build_parts: system=%d chars  user=%d chars.",
            len(system_prompt),
            len(user_prompt),
        )
        return system_prompt, user_prompt

    @staticmethod
    def system_instructions() -> str:
        """Return the fixed system instructions string (read-only access)."""
        return _SYSTEM_INSTRUCTIONS

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(question: str, context: str) -> None:
        """
        Validate that both inputs are non-empty strings.

        Raises:
            PromptBuildError: On any validation failure.
        """
        if not isinstance(question, str):
            raise PromptBuildError(
                f"question must be a str, got {type(question).__name__}."
            )
        if not question.strip():
            raise PromptBuildError(
                "question must not be empty or whitespace-only."
            )
        if not isinstance(context, str):
            raise PromptBuildError(
                f"context must be a str, got {type(context).__name__}."
            )
        if not context.strip():
            raise PromptBuildError(
                "context must not be empty or whitespace-only.  "
                "Ensure ContextBuilder produced a non-empty context string."
            )
