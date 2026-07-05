"""
llm/ollama_provider.py — Ollama local LLM implementation of ILLMProvider.

WHY OLLAMA
----------
Ollama runs open-weight models (Llama 3, Mistral, Phi-3, etc.) entirely
on the developer's own machine.  It requires no API key, no internet
access, and no usage billing.  For a personal knowledge engine over
private WhatsApp data, this is the privacy-correct default.

WHY HTTP DIRECTLY (NOT the official ollama Python library)
-----------------------------------------------------------
The ``ollama`` Python library adds a dependency and version-pins to a
specific API contract.  Ollama's HTTP API is stable, minimal, and
documented:
  POST /api/chat   — chat completion (OpenAI-compatible messages format)
  GET  /api/tags   — list available models (used for health_check)

Using ``urllib.request`` from the standard library:
  * Zero new dependencies.
  * Works in any Python 3.x environment without package managers.
  * The response schema is simple JSON — no deserialisation library needed.

SYSTEM + USER MESSAGE STRUCTURE
--------------------------------
Ollama's ``/api/chat`` endpoint accepts the same ``messages`` list as
OpenAI.  We send:
  [{"role": "system", "content": <grounding instructions>},
   {"role": "user",   "content": <context + question>}]

This maps exactly to how OpenAIProvider works — the caller sees a unified
interface regardless of which backend is active.

STREAMING
---------
``stream: false`` is sent so the entire response arrives in one JSON
object.  Streaming is useful for UI but adds complexity with no benefit
for a batch pipeline.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from config.llm_config import LLMConfig, PROVIDER_OLLAMA
from llm.interfaces import ILLMProvider, LLMResponse
from exceptions.exceptions import LLMProviderError

logger = logging.getLogger(__name__)

_CHAT_PATH    = "/api/chat"
_TAGS_PATH    = "/api/tags"
_TIMEOUT_BUMP = 5.0   # extra seconds added to config.timeout for connection overhead


class OllamaProvider(ILLMProvider):
    """
    LLM provider backed by a locally running Ollama instance.

    Parameters
    ----------
    config : LLMConfig
        Provider configuration.  ``config.provider`` must equal
        ``"ollama"``.  ``config.base_url`` defaults to
        ``"http://localhost:11434"``.

    Usage
    -----
    ::

        config   = LLMConfig(provider="ollama", model="llama3")
        provider = OllamaProvider(config)
        response = provider.generate(
            system_prompt="You are Nexora. Answer using only the context.",
            user_prompt="Context: ...\\n\\nQuestion: ...",
        )
        print(response.text)
        provider.close()
    """

    def __init__(self, config: LLMConfig) -> None:
        if config.provider != PROVIDER_OLLAMA:
            raise LLMProviderError(
                f"OllamaProvider requires config.provider == 'ollama', "
                f"got {config.provider!r}."
            )
        self._config = config
        self._base_url = (config.base_url or "http://localhost:11434").rstrip("/")
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
        Call Ollama /api/chat and return an LLMResponse.

        Args:
            system_prompt: Grounding instructions for the model.
            user_prompt:   Retrieved context + question.

        Returns:
            ``LLMResponse`` with the answer text and (estimated) usage.

        Raises:
            LLMProviderError: On connection failure, HTTP error, or
                              unexpected response structure.
        """
        self._assert_open()

        if not system_prompt or not system_prompt.strip():
            raise LLMProviderError("system_prompt must not be empty.")
        if not user_prompt or not user_prompt.strip():
            raise LLMProviderError("user_prompt must not be empty.")

        logger.info(
            "OllamaProvider.generate: model=%s  max_tokens=%d  temperature=%.2f",
            self._config.model,
            self._config.max_tokens,
            self._config.temperature,
        )

        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature":       self._config.temperature,
                "top_p":             self._config.top_p,
                "num_predict":       self._config.max_tokens,
                "presence_penalty":  self._config.presence_penalty,
                "frequency_penalty": self._config.frequency_penalty,
            },
        }

        data = self._post(_CHAT_PATH, payload)

        # Ollama /api/chat (non-streaming) returns:
        # {"model": ..., "message": {"role": "assistant", "content": ...},
        #  "prompt_eval_count": N, "eval_count": M, ...}
        message = data.get("message", {})
        text = message.get("content", "")

        prompt_tokens = data.get("prompt_eval_count", 0) or 0
        completion_tokens = data.get("eval_count", 0) or 0
        tokens_used = prompt_tokens + completion_tokens

        actual_model = data.get("model", self._config.model)

        logger.info(
            "OllamaProvider.generate: completed  tokens=%d  model=%s",
            tokens_used,
            actual_model,
        )

        return LLMResponse(
            text=text,
            tokens_used=tokens_used,
            model=actual_model,
            provider=PROVIDER_OLLAMA,
        )

    def health_check(self) -> bool:
        """
        Verify Ollama is running by calling GET /api/tags.

        Returns:
            ``True`` when Ollama responds (even if the requested model
            is not yet pulled).
            ``False`` on connection error.
        """
        self._assert_open()
        url = self._base_url + _TAGS_PATH

        try:
            req = urllib.request.Request(url, method="GET")
            timeout = min(self._config.timeout, 10.0)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read()   # consume body; status 200 = healthy
            logger.debug("OllamaProvider.health_check: PASS (url=%s)", url)
            return True
        except (urllib.error.URLError, OSError) as exc:
            logger.warning(
                "OllamaProvider.health_check: FAIL — %s  (url=%s)", exc, url
            )
            return False
        except Exception as exc:
            logger.warning(
                "OllamaProvider.health_check: unexpected error — %s", exc
            )
            return False

    @property
    def model_name(self) -> str:
        """The configured model identifier."""
        return self._config.model

    @property
    def provider_name(self) -> str:
        """Canonical provider name."""
        return PROVIDER_OLLAMA

    def close(self) -> None:
        """No persistent connection to release.  Idempotent."""
        if not self._closed:
            self._closed = True
            logger.debug("OllamaProvider closed.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, payload: dict) -> dict:
        """
        POST ``payload`` as JSON to ``self._base_url + path``.

        Returns:
            Parsed JSON response dict.

        Raises:
            LLMProviderError: On network error, HTTP error, or JSON parse
                              failure.
        """
        url = self._base_url + path
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        timeout = self._config.timeout + _TIMEOUT_BUMP

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama HTTP {exc.code} from {url}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMProviderError(
                f"Cannot reach Ollama at {url}: {exc.reason}.  "
                f"Is Ollama running?  Try: ollama serve"
            ) from exc
        except OSError as exc:
            raise LLMProviderError(
                f"Network error calling Ollama at {url}: {exc}"
            ) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"Ollama returned non-JSON response from {url}: {exc}"
            ) from exc

    def _assert_open(self) -> None:
        """Raise if close() has already been called."""
        if self._closed:
            raise LLMProviderError(
                "OllamaProvider has been closed.  Create a new instance."
            )
