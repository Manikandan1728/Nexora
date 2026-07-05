"""
llm/interfaces.py — Abstract interface for all LLM providers in Phase 6.

WHY AN INTERFACE EXISTS
-----------------------
The rest of Phase 6 (ContextBuilder, PromptBuilder, AnswerGenerator,
Phase6Pipeline) must be completely decoupled from the concrete LLM
backend.  If we called OpenAI or Ollama directly in the pipeline, every
test would need a live API endpoint, and switching providers would require
rewriting the entire generation layer.

``ILLMProvider`` defines the *contract* that any backend must satisfy.
``OpenAIProvider`` and ``OllamaProvider`` implement it.  The pipeline
depends only on this interface — the Dependency Inversion Principle.

WHY RAG NEEDS A GROUNDING PROMPT
---------------------------------
Large language models are trained on broad internet data.  Without
explicit grounding, they will answer from parametric memory even when that
memory is wrong, outdated, or irrelevant to the user's personal knowledge
base.  The interface forces callers to pass both a ``system_prompt`` (which
carries the grounding instruction) and a ``user_prompt`` (which carries
the question + context), making grounding structurally impossible to forget.

LLMResponse DESIGN
-------------------
Providers return ``LLMResponse`` rather than a plain string so that:
  * ``tokens_used`` is available for cost tracking without re-parsing.
  * ``model`` records exactly which model variant responded (useful when
    the backend routes to different versions).
  * Callers never need to import provider-specific response objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """
    Provider-agnostic response from a single LLM completion call.

    Attributes
    ----------
    text : str
        The generated completion text.  Never None; empty string if the
        provider returned no output.

    tokens_used : int
        Total tokens consumed (prompt + completion).  0 when the provider
        does not report usage.

    model : str
        The exact model identifier that generated the response.
        May differ from the requested model when the backend routes to a
        specific version (e.g. ``"gpt-4o-mini-2024-07-18"``).

    provider : str
        Canonical provider name: ``"openai"`` or ``"ollama"``.
    """

    text: str
    tokens_used: int
    model: str
    provider: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("LLMResponse.text must be a str.")
        if not isinstance(self.tokens_used, int) or self.tokens_used < 0:
            raise ValueError(
                f"LLMResponse.tokens_used must be a non-negative int, "
                f"got {self.tokens_used!r}."
            )
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("LLMResponse.model must be a non-empty string.")
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("LLMResponse.provider must be a non-empty string.")


class ILLMProvider(ABC):
    """
    Abstract base class for all LLM provider backends.

    Every method in this interface has a single responsibility:

    ``generate``       — produce a grounded completion from a prompt pair.
    ``health_check``   — verify the backend is reachable without generating text.
    ``model_name``     — return the configured model identifier.
    ``provider_name``  — return the canonical provider name.
    ``close``          — release held resources (HTTP clients, etc.).

    Implementations must never:
      * Store or log the content of ``system_prompt`` or ``user_prompt``.
      * Raise generic ``Exception`` — always raise ``LLMProviderError``.
      * Block indefinitely — honour the ``timeout`` from ``LLMConfig``.
    """

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResponse:
        """
        Generate a completion given a system prompt and a user prompt.

        The system prompt carries grounding instructions and safety rules.
        The user prompt carries the retrieved context + question.

        Args:
            system_prompt: Instructions for the model (grounding, persona,
                           tone, citation requirements).
            user_prompt:   The assembled context + question to answer.

        Returns:
            ``LLMResponse`` containing the completion text, token count,
            model name, and provider name.

        Raises:
            LLMProviderError: On any failure to produce a completion.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """
        Verify that the provider endpoint is reachable.

        Returns:
            ``True`` when the provider is healthy and can accept requests.
            ``False`` when the endpoint is unreachable but not outright
            broken (e.g. a temporary network timeout).

        Raises:
            LLMProviderError: Only on catastrophic failures (e.g. invalid
                              API key on OpenAI that would never succeed).
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier this provider is configured to use."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Canonical provider name: ``"openai"`` or ``"ollama"``."""

    @abstractmethod
    def close(self) -> None:
        """
        Release any resources held by this provider (HTTP clients, etc.).

        Must be idempotent — calling ``close()`` multiple times must not
        raise.
        """
