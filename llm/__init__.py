"""
llm — Phase 6 LLM provider sub-package.

Exposes the ILLMProvider interface and concrete provider implementations.
All generation code depends only on ILLMProvider — never on a specific
provider class directly.

    from llm import ILLMProvider, OpenAIProvider, OllamaProvider
"""

from llm.interfaces import ILLMProvider
from llm.openai_provider import OpenAIProvider
from llm.ollama_provider import OllamaProvider

__all__ = ["ILLMProvider", "OpenAIProvider", "OllamaProvider"]
