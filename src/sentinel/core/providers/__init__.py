"""Model provider implementations."""

from sentinel.core.providers.ollama import OllamaProvider
from sentinel.core.providers.openai_compat import OpenAICompatibleProvider

__all__ = ["OllamaProvider", "OpenAICompatibleProvider"]
