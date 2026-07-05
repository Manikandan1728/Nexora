"""
config/llm_config.py — Configuration for Phase 6 LLM providers.

WHY THIS MODULE EXISTS
----------------------
Hard-coding model names, temperatures, and API keys throughout the
generation layer creates brittle, untestable code. A single validated
configuration object:

  * Makes every tunable visible in one place.
  * Allows environment-variable overrides so the same code runs in
    development (Ollama), CI (mocked), and production (OpenAI) without
    code changes — the twelve-factor app principle.
  * Enables dependency injection: tests pass a config with a fake
    provider; production passes a real one.
  * Keeps secrets out of source code entirely.

ENVIRONMENT VARIABLE OVERRIDES
-------------------------------
  NEXORA_LLM_PROVIDER          -> provider  ("openai" | "ollama")
  NEXORA_LLM_MODEL             -> model
  NEXORA_LLM_TEMPERATURE       -> temperature
  NEXORA_LLM_MAX_TOKENS        -> max_tokens
  NEXORA_LLM_TOP_P             -> top_p
  NEXORA_LLM_PRESENCE_PENALTY  -> presence_penalty
  NEXORA_LLM_FREQUENCY_PENALTY -> frequency_penalty
  NEXORA_LLM_TIMEOUT           -> timeout
  OPENAI_API_KEY               -> api_key   (standard OpenAI convention)
  NEXORA_LLM_BASE_URL          -> base_url  (for Ollama or proxies)
  NEXORA_CONTEXT_TOKEN_BUDGET  -> context_token_budget
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Valid provider names
# ---------------------------------------------------------------------------
PROVIDER_OPENAI: str = "openai"
PROVIDER_OLLAMA: str = "ollama"
_VALID_PROVIDERS: frozenset = frozenset({PROVIDER_OPENAI, PROVIDER_OLLAMA})

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_PROVIDER: str = "ollama"
_DEFAULT_OPENAI_MODEL: str = "gpt-4o-mini"
_DEFAULT_OLLAMA_MODEL: str = "llama3"
_DEFAULT_TEMPERATURE: float = 0.2
_DEFAULT_MAX_TOKENS: int = 1024
_DEFAULT_TOP_P: float = 1.0
_DEFAULT_PRESENCE_PENALTY: float = 0.0
_DEFAULT_FREQUENCY_PENALTY: float = 0.0
_DEFAULT_TIMEOUT: float = 60.0
_DEFAULT_OLLAMA_BASE_URL: str = "http://localhost:11434"
_DEFAULT_CONTEXT_TOKEN_BUDGET: int = 3000

# Sentinel — distinguishes "caller did not pass model" from "caller passed None"
_MODEL_NOT_SET: str = "__nexora_model_not_set__"


@dataclass
class LLMConfig:
    """
    Configuration for an LLM provider used in Phase 6.

    Parameters
    ----------
    provider : str
        Which backend to use.  Must be ``"openai"`` or ``"ollama"``.
        Default: ``"ollama"`` (runs locally, no API key required).

    model : str
        Model identifier passed to the provider.
        - OpenAI: ``"gpt-4o-mini"``, ``"gpt-4o"``, ``"o3-mini"``, ...
        - Ollama: ``"llama3"``, ``"mistral"``, ``"phi3"``, ...
        When not supplied, the default is chosen based on ``provider``:
          - ``"openai"``  -> ``"gpt-4o-mini"``
          - ``"ollama"``  -> ``"llama3"``
        Priority: explicit arg > NEXORA_LLM_MODEL env var > provider default.

    temperature : float
        Sampling temperature in [0.0, 2.0].  Lower values make output
        more deterministic — important for factual RAG answers.
        Default: 0.2.

    max_tokens : int
        Maximum number of completion tokens the model may generate.
        Default: 1024.

    top_p : float
        Nucleus sampling probability mass in (0.0, 1.0].
        Default: 1.0 (disabled).

    presence_penalty : float
        Penalises tokens based on their presence in the text so far.
        Range: [-2.0, 2.0].  Default: 0.0.

    frequency_penalty : float
        Penalises tokens based on their frequency in the text so far.
        Range: [-2.0, 2.0].  Default: 0.0.

    timeout : float
        Request timeout in seconds.  Default: 60.0.

    api_key : str, optional
        Provider API key.  For OpenAI, read from ``OPENAI_API_KEY`` if
        not set explicitly.  Never stored in source code.

    base_url : str, optional
        Custom base URL.  Required for Ollama (``http://localhost:11434``).
        Also used to point at OpenAI-compatible proxies.

    context_token_budget : int
        Maximum number of tokens the context builder may include from
        retrieved documents.  Prevents the prompt from exceeding the
        model's context window.
        Default: 3000.
    """

    provider: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_LLM_PROVIDER", _DEFAULT_PROVIDER
        )
    )
    # model defaults to the sentinel so __post_init__ can detect
    # whether the caller supplied an explicit value.
    model: str = field(
        default_factory=lambda: os.environ.get(
            "NEXORA_LLM_MODEL", _MODEL_NOT_SET
        )
    )
    temperature: float = field(
        default_factory=lambda: float(
            os.environ.get("NEXORA_LLM_TEMPERATURE", str(_DEFAULT_TEMPERATURE))
        )
    )
    max_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("NEXORA_LLM_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS))
        )
    )
    top_p: float = field(
        default_factory=lambda: float(
            os.environ.get("NEXORA_LLM_TOP_P", str(_DEFAULT_TOP_P))
        )
    )
    presence_penalty: float = field(
        default_factory=lambda: float(
            os.environ.get(
                "NEXORA_LLM_PRESENCE_PENALTY", str(_DEFAULT_PRESENCE_PENALTY)
            )
        )
    )
    frequency_penalty: float = field(
        default_factory=lambda: float(
            os.environ.get(
                "NEXORA_LLM_FREQUENCY_PENALTY", str(_DEFAULT_FREQUENCY_PENALTY)
            )
        )
    )
    timeout: float = field(
        default_factory=lambda: float(
            os.environ.get("NEXORA_LLM_TIMEOUT", str(_DEFAULT_TIMEOUT))
        )
    )
    api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY")
    )
    base_url: Optional[str] = field(
        default_factory=lambda: os.environ.get("NEXORA_LLM_BASE_URL")
    )
    context_token_budget: int = field(
        default_factory=lambda: int(
            os.environ.get(
                "NEXORA_CONTEXT_TOKEN_BUDGET", str(_DEFAULT_CONTEXT_TOKEN_BUDGET)
            )
        )
    )

    def __post_init__(self) -> None:
        """Validate all fields and resolve model default after provider is known."""

        # ── provider ─────────────────────────────────────────────────
        if self.provider not in _VALID_PROVIDERS:
            raise ValueError(
                f"LLMConfig.provider must be one of {sorted(_VALID_PROVIDERS)}, "
                f"got {self.provider!r}."
            )

        # ── model — resolve default now that provider is known ────────
        # Priority: explicit arg > NEXORA_LLM_MODEL env var > provider default
        if self.model == _MODEL_NOT_SET:
            # Neither the caller nor the env var supplied a model.
            # Choose the provider-appropriate default.
            if self.provider == PROVIDER_OPENAI:
                object.__setattr__(self, "model", _DEFAULT_OPENAI_MODEL)
            else:
                object.__setattr__(self, "model", _DEFAULT_OLLAMA_MODEL)

        if not self.model or not self.model.strip():
            raise ValueError("LLMConfig.model must not be empty.")

        # ── numeric fields ────────────────────────────────────────────
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError(
                f"LLMConfig.temperature must be in [0.0, 2.0], "
                f"got {self.temperature!r}."
            )

        if self.max_tokens < 1:
            raise ValueError(
                f"LLMConfig.max_tokens must be >= 1, got {self.max_tokens!r}."
            )

        if not (0.0 < self.top_p <= 1.0):
            raise ValueError(
                f"LLMConfig.top_p must be in (0.0, 1.0], got {self.top_p!r}."
            )

        if not (-2.0 <= self.presence_penalty <= 2.0):
            raise ValueError(
                f"LLMConfig.presence_penalty must be in [-2.0, 2.0], "
                f"got {self.presence_penalty!r}."
            )

        if not (-2.0 <= self.frequency_penalty <= 2.0):
            raise ValueError(
                f"LLMConfig.frequency_penalty must be in [-2.0, 2.0], "
                f"got {self.frequency_penalty!r}."
            )

        if self.timeout <= 0:
            raise ValueError(
                f"LLMConfig.timeout must be positive, got {self.timeout!r}."
            )

        if self.context_token_budget < 100:
            raise ValueError(
                f"LLMConfig.context_token_budget must be >= 100, "
                f"got {self.context_token_budget!r}."
            )

        # ── Ollama base_url ───────────────────────────────────────────
        # Always set a base_url for Ollama if not explicitly provided.
        if self.provider == PROVIDER_OLLAMA and not self.base_url:
            object.__setattr__(self, "base_url", _DEFAULT_OLLAMA_BASE_URL)

    @property
    def is_openai(self) -> bool:
        """True when the configured provider is OpenAI."""
        return self.provider == PROVIDER_OPENAI

    @property
    def is_ollama(self) -> bool:
        """True when the configured provider is Ollama."""
        return self.provider == PROVIDER_OLLAMA

    def __repr__(self) -> str:
        # Never include the API key in repr
        return (
            f"LLMConfig(provider={self.provider!r}, model={self.model!r}, "
            f"temperature={self.temperature}, max_tokens={self.max_tokens}, "
            f"base_url={self.base_url!r})"
        )
