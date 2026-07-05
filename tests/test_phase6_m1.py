"""
tests/test_phase6_m1.py — Milestone 1 unit tests for Phase 6 LLM providers.

ALL TESTS ARE FULLY ISOLATED.
  - No real OpenAI API calls are made.
  - No real Ollama server is required.
  - HTTP is mocked using unittest.mock.patch and a fake urllib handler.
  - Tests verify the interface contract, provider construction, generate()
    behaviour, health_check() behaviour, close() idempotency, and all
    error handling paths.
"""

from __future__ import annotations

import json
import unittest.mock as mock
from typing import List
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from config.llm_config import LLMConfig, PROVIDER_OPENAI, PROVIDER_OLLAMA
from llm.interfaces import ILLMProvider, LLMResponse
from llm.openai_provider import OpenAIProvider
from llm.ollama_provider import OllamaProvider
from exceptions.exceptions import LLMProviderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openai_cfg(**kwargs) -> LLMConfig:
    defaults = dict(
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-test-fake-key",
        temperature=0.2,
        max_tokens=512,
    )
    defaults.update(kwargs)
    return LLMConfig(**defaults)


def _ollama_cfg(**kwargs) -> LLMConfig:
    defaults = dict(
        provider="ollama",
        model="llama3",
        base_url="http://localhost:11434",
    )
    defaults.update(kwargs)
    return LLMConfig(**defaults)


def _make_openai_response(text: str, total_tokens: int = 42, model: str = "gpt-4o-mini"):
    """Build a mock openai ChatCompletion response object."""
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    response.usage.total_tokens = total_tokens
    response.model = model
    return response


def _make_ollama_response(text: str, model: str = "llama3",
                          prompt_tokens: int = 10, eval_tokens: int = 20) -> dict:
    """Build a fake Ollama /api/chat JSON response dict."""
    return {
        "model": model,
        "message": {"role": "assistant", "content": text},
        "prompt_eval_count": prompt_tokens,
        "eval_count": eval_tokens,
    }


# ---------------------------------------------------------------------------
# 1. LLMConfig tests
# ---------------------------------------------------------------------------

class TestLLMConfig:

    def test_openai_config_defaults(self):
        # When model is explicitly specified, it must be honoured
        cfg = LLMConfig(provider="openai", model="gpt-4o-mini", api_key="sk-x")
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o-mini"
        assert 0.0 <= cfg.temperature <= 2.0
        assert cfg.max_tokens >= 1

    def test_ollama_config_defaults(self):
        cfg = LLMConfig(provider="ollama")
        assert cfg.provider == "ollama"
        assert cfg.model == "llama3"
        assert cfg.base_url == "http://localhost:11434"

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="provider"):
            LLMConfig(provider="anthropic")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            LLMConfig(provider="ollama", model="")

    def test_temperature_out_of_range_raises(self):
        with pytest.raises(ValueError, match="temperature"):
            LLMConfig(provider="ollama", temperature=3.0)

    def test_max_tokens_zero_raises(self):
        with pytest.raises(ValueError, match="max_tokens"):
            LLMConfig(provider="ollama", max_tokens=0)

    def test_top_p_zero_raises(self):
        with pytest.raises(ValueError, match="top_p"):
            LLMConfig(provider="ollama", top_p=0.0)

    def test_timeout_zero_raises(self):
        with pytest.raises(ValueError, match="timeout"):
            LLMConfig(provider="ollama", timeout=0.0)

    def test_context_token_budget_too_small_raises(self):
        with pytest.raises(ValueError, match="context_token_budget"):
            LLMConfig(provider="ollama", context_token_budget=50)

    def test_is_openai_property(self):
        assert LLMConfig(provider="openai", api_key="sk-x").is_openai is True
        assert LLMConfig(provider="ollama").is_openai is False

    def test_is_ollama_property(self):
        assert LLMConfig(provider="ollama").is_ollama is True
        assert LLMConfig(provider="openai", api_key="sk-x").is_ollama is False

    def test_repr_does_not_contain_api_key(self):
        cfg = LLMConfig(provider="openai", api_key="sk-super-secret")
        assert "sk-super-secret" not in repr(cfg)

    def test_ollama_sets_default_base_url(self):
        cfg = LLMConfig(provider="ollama", base_url=None)
        assert cfg.base_url == "http://localhost:11434"


# ---------------------------------------------------------------------------
# 2. LLMResponse model tests
# ---------------------------------------------------------------------------

class TestLLMResponse:

    def test_valid_construction(self):
        r = LLMResponse(text="Hello", tokens_used=10, model="m", provider="openai")
        assert r.text == "Hello"
        assert r.tokens_used == 10

    def test_empty_text_allowed(self):
        # Empty text is valid (model may produce no output)
        r = LLMResponse(text="", tokens_used=0, model="m", provider="openai")
        assert r.text == ""

    def test_negative_tokens_raises(self):
        with pytest.raises(ValueError, match="tokens_used"):
            LLMResponse(text="x", tokens_used=-1, model="m", provider="openai")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            LLMResponse(text="x", tokens_used=0, model="", provider="openai")

    def test_empty_provider_raises(self):
        with pytest.raises(ValueError, match="provider"):
            LLMResponse(text="x", tokens_used=0, model="m", provider="")


# ---------------------------------------------------------------------------
# 3. ILLMProvider interface tests
# ---------------------------------------------------------------------------

class TestILLMProviderInterface:

    def test_is_abstract(self):
        with pytest.raises(TypeError):
            ILLMProvider()  # type: ignore

    def test_concrete_must_implement_all_methods(self):
        """A partial implementation that skips generate() cannot be instantiated."""
        class Incomplete(ILLMProvider):
            def health_check(self): return True
            @property
            def model_name(self): return "x"
            @property
            def provider_name(self): return "x"
            def close(self): pass

        with pytest.raises(TypeError):
            Incomplete()


# ---------------------------------------------------------------------------
# 4. OpenAIProvider tests (no real API calls)
# ---------------------------------------------------------------------------

class TestOpenAIProvider:

    def _provider(self, **kwargs) -> OpenAIProvider:
        return OpenAIProvider(_openai_cfg(**kwargs))

    def test_wrong_provider_raises(self):
        with pytest.raises(LLMProviderError, match="openai"):
            OpenAIProvider(_ollama_cfg())

    def test_provider_name(self):
        p = self._provider()
        assert p.provider_name == PROVIDER_OPENAI

    def test_model_name(self):
        p = self._provider(model="gpt-4o")
        assert p.model_name == "gpt-4o"

    def test_generate_returns_llm_response(self):
        p = self._provider()
        mock_resp = _make_openai_response("The answer is 42.", total_tokens=55)
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_resp
            mock_get.return_value = mock_client

            result = p.generate("sys", "user")

        assert isinstance(result, LLMResponse)
        assert result.text == "The answer is 42."
        assert result.tokens_used == 55
        assert result.provider == PROVIDER_OPENAI

    def test_generate_passes_correct_params(self):
        p = self._provider(temperature=0.5, max_tokens=200)
        mock_resp = _make_openai_response("ok")
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_resp
            mock_get.return_value = mock_client

            p.generate("system text", "user text")
            call_kwargs = mock_client.chat.completions.create.call_args[1]

        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 200
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"

    def test_generate_empty_system_prompt_raises(self):
        p = self._provider()
        with pytest.raises(LLMProviderError, match="system_prompt"):
            p.generate("", "user")

    def test_generate_empty_user_prompt_raises(self):
        p = self._provider()
        with pytest.raises(LLMProviderError, match="user_prompt"):
            p.generate("sys", "")

    def test_generate_api_error_raises_llm_provider_error(self):
        p = self._provider()
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("HTTP 500")
            mock_get.return_value = mock_client

            with pytest.raises(LLMProviderError, match="500"):
                p.generate("sys", "user")

    def test_generate_empty_choices_raises(self):
        p = self._provider()
        mock_resp = MagicMock()
        mock_resp.choices = []
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_resp
            mock_get.return_value = mock_client

            with pytest.raises(LLMProviderError, match="empty choices"):
                p.generate("sys", "user")

    def test_health_check_success(self):
        p = self._provider()
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.models.list.return_value = MagicMock()
            mock_get.return_value = mock_client

            assert p.health_check() is True

    def test_health_check_connection_error_returns_false(self):
        p = self._provider()
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.models.list.side_effect = Exception("Connection refused")
            mock_get.return_value = mock_client

            assert p.health_check() is False

    def test_health_check_401_raises_llm_provider_error(self):
        p = self._provider()
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.models.list.side_effect = Exception("401 unauthorized api_key")
            mock_get.return_value = mock_client

            with pytest.raises(LLMProviderError, match="invalid"):
                p.health_check()

    def test_close_is_idempotent(self):
        p = self._provider()
        p.close()
        p.close()  # must not raise

    def test_generate_after_close_raises(self):
        p = self._provider()
        p.close()
        with pytest.raises(LLMProviderError, match="closed"):
            p.generate("sys", "user")

    def test_generate_uses_none_usage_gracefully(self):
        """When response.usage is None, tokens_used should be 0."""
        p = self._provider()
        mock_resp = _make_openai_response("answer")
        mock_resp.usage = None
        with patch.object(p, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_resp
            mock_get.return_value = mock_client

            result = p.generate("sys", "user")
        assert result.tokens_used == 0


# ---------------------------------------------------------------------------
# 5. OllamaProvider tests (HTTP mocked via patch on _post)
# ---------------------------------------------------------------------------

class TestOllamaProvider:

    def _provider(self, **kwargs) -> OllamaProvider:
        return OllamaProvider(_ollama_cfg(**kwargs))

    def test_wrong_provider_raises(self):
        with pytest.raises(LLMProviderError, match="ollama"):
            OllamaProvider(_openai_cfg())

    def test_provider_name(self):
        p = self._provider()
        assert p.provider_name == PROVIDER_OLLAMA

    def test_model_name(self):
        p = self._provider(model="mistral")
        assert p.model_name == "mistral"

    def test_generate_returns_llm_response(self):
        p = self._provider()
        fake_resp = _make_ollama_response("Nexora answer here.", eval_tokens=30)
        with patch.object(p, "_post", return_value=fake_resp):
            result = p.generate("system", "user")

        assert isinstance(result, LLMResponse)
        assert result.text == "Nexora answer here."
        assert result.tokens_used == 40   # 10 + 30
        assert result.provider == PROVIDER_OLLAMA

    def test_generate_posts_to_correct_path(self):
        p = self._provider()
        fake_resp = _make_ollama_response("ok")
        with patch.object(p, "_post", return_value=fake_resp) as mock_post:
            p.generate("sys", "user")
            path_arg = mock_post.call_args[0][0]

        assert path_arg == "/api/chat"

    def test_generate_includes_system_and_user_messages(self):
        p = self._provider()
        fake_resp = _make_ollama_response("ok")
        with patch.object(p, "_post", return_value=fake_resp) as mock_post:
            p.generate("my system", "my user question")
            payload = mock_post.call_args[0][1]

        messages = payload["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "my system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "my user question"

    def test_generate_stream_is_false(self):
        p = self._provider()
        fake_resp = _make_ollama_response("ok")
        with patch.object(p, "_post", return_value=fake_resp) as mock_post:
            p.generate("sys", "user")
            payload = mock_post.call_args[0][1]

        assert payload["stream"] is False

    def test_generate_empty_system_prompt_raises(self):
        p = self._provider()
        with pytest.raises(LLMProviderError, match="system_prompt"):
            p.generate("", "user")

    def test_generate_empty_user_prompt_raises(self):
        p = self._provider()
        with pytest.raises(LLMProviderError, match="user_prompt"):
            p.generate("sys", "")

    def test_generate_http_error_raises_llm_provider_error(self):
        p = self._provider()
        with patch.object(p, "_post", side_effect=LLMProviderError("HTTP 404")):
            with pytest.raises(LLMProviderError, match="404"):
                p.generate("sys", "user")

    def test_health_check_success(self):
        p = self._provider()
        fake_body = json.dumps({"models": []}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = fake_body

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert p.health_check() is True

    def test_health_check_connection_refused_returns_false(self):
        p = self._provider()
        import urllib.error
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            assert p.health_check() is False

    def test_close_is_idempotent(self):
        p = self._provider()
        p.close()
        p.close()   # must not raise

    def test_generate_after_close_raises(self):
        p = self._provider()
        p.close()
        with pytest.raises(LLMProviderError, match="closed"):
            p.generate("sys", "user")

    def test_generate_missing_message_key_produces_empty_text(self):
        """If Ollama response lacks 'message', text should be empty string."""
        p = self._provider()
        incomplete = {"model": "llama3", "eval_count": 5}
        with patch.object(p, "_post", return_value=incomplete):
            result = p.generate("sys", "user")
        assert result.text == ""
        assert result.tokens_used == 5

    def test_generate_token_count_zero_when_missing(self):
        p = self._provider()
        no_tokens = {"model": "llama3", "message": {"role": "assistant", "content": "hi"}}
        with patch.object(p, "_post", return_value=no_tokens):
            result = p.generate("sys", "user")
        assert result.tokens_used == 0


# ---------------------------------------------------------------------------
# 6. Provider selection tests
# ---------------------------------------------------------------------------

class TestProviderSelection:

    def test_openai_provider_implements_interface(self):
        p = OpenAIProvider(_openai_cfg())
        assert isinstance(p, ILLMProvider)

    def test_ollama_provider_implements_interface(self):
        p = OllamaProvider(_ollama_cfg())
        assert isinstance(p, ILLMProvider)

    def test_llm_package_exports_all_symbols(self):
        from llm import ILLMProvider, OpenAIProvider, OllamaProvider
        assert ILLMProvider is not None
        assert OpenAIProvider is not None
        assert OllamaProvider is not None
