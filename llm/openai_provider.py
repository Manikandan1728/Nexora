"""
llm/openai_provider.py — OpenAI chat.completions implementation of ILLMProvider.

WHY chat.completions RATHER THAN responses API
-----------------------------------------------
The OpenAI ``responses`` API (added in openai >= 2.x) is designed for
multi-turn agentic workflows with tool use.  Its parameter surface differs
from ``chat.completions``: it uses ``input``/``instructions`` instead of
``messages``, and ``max_output_tokens`` instead of ``max_tokens``.
Crucially, it does not expose ``temperature`` or ``top_p`` at the
``responses.create`` level — those parameters are controlled at the
``prompt`` object level, which requires a more complex call structure.

For RAG answer generation, ``chat.completions.create`` is the correct API:
  * Direct ``messages`` list maps naturally to system + user structure.
  * ``temperature``, ``top_p``, ``presence_penalty``, ``frequency_penalty``
    all control generation quality for factual grounding.
  * ``usage`` is always reported, enabling cost tracking.
  * It is stable across all OpenAI-compatible providers and proxies.

SECURITY
--------
The API key is read from ``LLMConfig.api_key`` which itself reads from the
``OPENAI_API_KEY`` environment variable.  The key is passed only to the
``OpenAI`` client constructor — it is never logged, printed, or stored as
an instance attribute accessible outside the constructor.

LAZY CLIENT INITIALISATION
---------------------------
The ``OpenAI`` client is constructed on the first ``generate()`` call, not
at ``__init__`` time.  This means importing or instantiating
``OpenAIProvider`` in tests does not require ``OPENAI_API_KEY`` to be set —
the requirement is deferred to actual use.
"""

from __future__ import annotations

import logging
from typing import Optional

from config.llm_config import LLMConfig, PROVIDER_OPENAI
from llm.interfaces import ILLMProvider, LLMResponse
from exceptions.exceptions import LLMProviderError

logger = logging.getLogger(__name__)


class OpenAIProvider(ILLMProvider):
    """
    LLM provider backed by the OpenAI chat.completions API.

    Parameters
    ----------
    config : LLMConfig
        Provider configuration.  ``config.provider`` must equal
        ``"openai"``, and ``config.api_key`` must be set (or the
        ``OPENAI_API_KEY`` environment variable must be present).

    Usage
    -----
    ::

        config = LLMConfig(provider="openai", model="gpt-4o-mini",
                           api_key="sk-...")
        provider = OpenAIProvider(config)
        response = provider.generate(
            system_prompt="You are Nexora. Answer using only the context.",
            user_prompt="Context: ...\\n\\nQuestion: ...",
        )
        print(response.text)
        provider.close()
    """

    def __init__(self, config: LLMConfig) -> None:
        if config.provider != PROVIDER_OPENAI:
            raise LLMProviderError(
                f"OpenAIProvider requires config.provider == 'openai', "
                f"got {config.provider!r}."
            )
        self._config = config
        self._client = None   # lazy-initialised on first generate() call
        self._closed = False

    # ------------------------------------------------------------------
    # ILLMProvider implementation
    # ------------------------------------------------------------------

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResponse:
        """
        Call OpenAI chat.completions.create and return an LLMResponse.

        Args:
            system_prompt: Grounding instructions for the model.
            user_prompt:   Retrieved context + question.

        Returns:
            ``LLMResponse`` with the answer text and usage statistics.

        Raises:
            LLMProviderError: On any OpenAI API error or invalid response.
        """
        self._assert_open()

        if not system_prompt or not system_prompt.strip():
            raise LLMProviderError("system_prompt must not be empty.")
        if not user_prompt or not user_prompt.strip():
            raise LLMProviderError("user_prompt must not be empty.")

        client = self._get_client()

        # Log operational metadata only — never log prompt content
        logger.info(
            "OpenAIProvider.generate: model=%s  max_tokens=%d  temperature=%.2f",
            self._config.model,
            self._config.max_tokens,
            self._config.temperature,
        )

        try:
            response = client.chat.completions.create(
                model=self._config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
                top_p=self._config.top_p,
                presence_penalty=self._config.presence_penalty,
                frequency_penalty=self._config.frequency_penalty,
                timeout=self._config.timeout,
            )
        except Exception as exc:
            raise LLMProviderError(
                f"OpenAI chat.completions.create failed: {exc}"
            ) from exc

        # Extract text — guard against None choices
        if not response.choices:
            raise LLMProviderError(
                "OpenAI returned an empty choices list.  "
                "The model may have been filtered or rate-limited."
            )

        text = response.choices[0].message.content or ""

        # Token usage (always present for chat.completions)
        tokens_used = 0
        if response.usage:
            tokens_used = response.usage.total_tokens or 0

        # Actual model version the backend routed to
        actual_model = response.model or self._config.model

        logger.info(
            "OpenAIProvider.generate: completed  tokens=%d  model=%s",
            tokens_used,
            actual_model,
        )

        return LLMResponse(
            text=text,
            tokens_used=tokens_used,
            model=actual_model,
            provider=PROVIDER_OPENAI,
        )

    def health_check(self) -> bool:
        """
        Verify the API key is set and the endpoint is reachable by
        listing available models (a lightweight read-only call).

        Returns:
            ``True`` when the API key is valid and the endpoint responds.
            ``False`` on connection errors.

        Raises:
            LLMProviderError: When the API key is definitively invalid
                              (HTTP 401).
        """
        self._assert_open()
        client = self._get_client()

        try:
            # Listing models is the lightest non-generating API call
            client.models.list()
            logger.debug("OpenAIProvider.health_check: PASS")
            return True
        except Exception as exc:
            err_str = str(exc).lower()
            if "401" in err_str or "unauthorized" in err_str or "api_key" in err_str:
                raise LLMProviderError(
                    f"OpenAI API key is invalid or missing: {exc}"
                ) from exc
            logger.warning("OpenAIProvider.health_check: FAIL — %s", exc)
            return False

    @property
    def model_name(self) -> str:
        """The configured model identifier."""
        return self._config.model

    @property
    def provider_name(self) -> str:
        """Canonical provider name."""
        return PROVIDER_OPENAI

    def close(self) -> None:
        """Release the HTTP client.  Idempotent."""
        if not self._closed:
            self._client = None
            self._closed = True
            logger.debug("OpenAIProvider closed.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Lazy-initialise and return the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                kwargs: dict = {"timeout": self._config.timeout}
                if self._config.api_key:
                    kwargs["api_key"] = self._config.api_key
                if self._config.base_url:
                    kwargs["base_url"] = self._config.base_url

                self._client = OpenAI(**kwargs)
                logger.info(
                    "OpenAIProvider: client initialised for model '%s'.",
                    self._config.model,
                )
            except Exception as exc:
                raise LLMProviderError(
                    f"Failed to initialise OpenAI client: {exc}"
                ) from exc
        return self._client

    def _assert_open(self) -> None:
        """Raise if close() has already been called."""
        if self._closed:
            raise LLMProviderError(
                "OpenAIProvider has been closed.  Create a new instance."
            )
