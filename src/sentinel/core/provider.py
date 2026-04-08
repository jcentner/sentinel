"""Model provider protocol — abstracts all LLM interaction.

See ADR-010 for the design rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sentinel.config import SentinelConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    """Response from a model provider's generate() call."""

    text: str
    token_count: int | None = None
    duration_ms: float | None = None


@runtime_checkable
class ModelProvider(Protocol):
    """Protocol for LLM model providers.

    Implementations must support text generation, embedding, and health checks.
    The protocol is provider-agnostic — Ollama, OpenAI-compatible endpoints,
    and custom providers all implement the same interface.
    """

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
        num_ctx: int = 2048,
        json_output: bool = False,
    ) -> LLMResponse:
        """Generate a text completion.

        Args:
            prompt: The user prompt text.
            system: Optional system prompt.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens to generate.
            num_ctx: Context window size hint (provider may ignore).
            json_output: Request structured JSON output if supported.

        Returns:
            LLMResponse with the generated text and optional metrics.
        """
        ...

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed a batch of texts into vectors.

        Returns a list of embedding vectors (one per input text),
        or None if embedding is not supported or fails.
        """
        ...

    def check_health(self) -> bool:
        """Check if the provider is reachable and operational."""
        ...


def create_provider(config: SentinelConfig) -> ModelProvider:
    """Create a ModelProvider instance from configuration.

    Args:
        config: Sentinel configuration with provider, model, and endpoint fields.

    Returns:
        A ModelProvider implementation (OllamaProvider or OpenAICompatibleProvider).

    Raises:
        ValueError: If the provider name is not recognized.
    """
    from sentinel.core.providers.ollama import OllamaProvider
    from sentinel.core.providers.openai_compat import OpenAICompatibleProvider

    if config.provider == "ollama":
        return OllamaProvider(
            model=config.model,
            ollama_url=config.ollama_url,
            embed_model=config.embed_model,
        )
    elif config.provider == "openai":
        if not config.api_base:
            raise ValueError(
                "provider = 'openai' requires api_base to be set "
                "(e.g., 'https://api.openai.com' or your Azure endpoint)"
            )
        # Log privacy warning for cloud providers
        logger.warning(
            "Provider 'openai' configured — code excerpts will be sent to %s",
            config.api_base,
        )
        return OpenAICompatibleProvider(
            model=config.model,
            api_base=config.api_base,
            api_key_env=config.api_key_env,
            embed_model=config.embed_model,
        )
    elif config.provider == "azure":
        from sentinel.core.providers.azure import AzureProvider

        if not config.api_base:
            raise ValueError(
                "provider = 'azure' requires api_base to be set "
                "(e.g., 'https://<resource>.services.ai.azure.com')"
            )
        logger.warning(
            "Provider 'azure' configured — code excerpts will be sent to %s",
            config.api_base,
        )
        return AzureProvider(
            model=config.model,
            api_base=config.api_base,
            embed_model=config.embed_model,
        )
    else:
        raise ValueError(
            f"Unknown provider: {config.provider!r}. "
            f"Valid providers: 'ollama', 'openai', 'azure'"
        )
