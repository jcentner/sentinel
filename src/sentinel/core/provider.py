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

    Error contract (TD-019):
        generate() — Raises on failure (httpx exceptions, ValueError, etc.).
            Callers must wrap in try/except. Cloud providers include retry
            logic for transient failures before raising.
        embed() — Returns None on failure (all exceptions caught internally).
            Callers check for None. This asymmetry is intentional: embedding
            failures are non-critical (context enrichment degrades gracefully),
            while generation failures are critical (judge/detector LLM calls
            must surface errors to the pipeline for proper handling).
        check_health() — Returns False on failure (never raises).
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

        Raises:
            httpx.HTTPStatusError: On non-retryable HTTP errors.
            httpx.TimeoutException: On timeout after retries exhausted.
            httpx.ConnectError: On connection failure after retries exhausted.
        """
        ...

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed a batch of texts into vectors.

        Returns a list of embedding vectors (one per input text),
        or None if embedding is not supported or fails. All exceptions
        are caught internally — callers should check for None.
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
    return _create_provider_from_fields(
        provider=config.provider,
        model=config.model,
        ollama_url=config.ollama_url,
        api_base=config.api_base,
        api_key_env=config.api_key_env,
        embed_model=config.embed_model,
    )


def create_provider_for_detector(
    detector_name: str,
    config: SentinelConfig,
) -> ModelProvider | None:
    """Create a per-detector ModelProvider, falling back to global config.

    Returns None if the global provider would be used (caller should use
    the shared global provider instead to avoid duplicate connections).
    """
    from sentinel.config import ProviderOverride

    overrides: dict[str, ProviderOverride] = config.detector_providers
    override = overrides.get(detector_name)
    if override is None:
        return None  # Use global provider

    # Merge: override fields take precedence, empty strings fall back to global
    provider = override.provider or config.provider
    model = override.model or config.model
    api_base = override.api_base or config.api_base
    api_key_env = override.api_key_env or config.api_key_env

    # If nothing actually differs from global, return None
    if (provider == config.provider and model == config.model
            and api_base == config.api_base and api_key_env == config.api_key_env):
        return None

    logger.info(
        "Using per-detector provider for %s: %s/%s",
        detector_name, provider, model,
    )
    return _create_provider_from_fields(
        provider=provider,
        model=model,
        ollama_url=config.ollama_url,
        api_base=api_base,
        api_key_env=api_key_env,
        embed_model=config.embed_model,
    )


def _create_provider_from_fields(
    *,
    provider: str,
    model: str,
    ollama_url: str,
    api_base: str,
    api_key_env: str,
    embed_model: str,
) -> ModelProvider:
    """Internal factory: create a provider from explicit field values."""
    from sentinel.core.providers.ollama import OllamaProvider
    from sentinel.core.providers.openai_compat import OpenAICompatibleProvider

    if provider == "ollama":
        return OllamaProvider(
            model=model,
            ollama_url=ollama_url,
            embed_model=embed_model,
        )
    elif provider == "openai":
        if not api_base:
            raise ValueError(
                "provider = 'openai' requires api_base to be set "
                "(e.g., 'https://api.openai.com' or your Azure endpoint)"
            )
        logger.warning(
            "Provider 'openai' configured — code excerpts will be sent to %s",
            api_base,
        )
        return OpenAICompatibleProvider(
            model=model,
            api_base=api_base,
            api_key_env=api_key_env,
            embed_model=embed_model,
        )
    elif provider == "azure":
        from sentinel.core.providers.azure import AzureProvider

        if not api_base:
            raise ValueError(
                "provider = 'azure' requires api_base to be set "
                "(e.g., 'https://<resource>.services.ai.azure.com')"
            )
        logger.warning(
            "Provider 'azure' configured — code excerpts will be sent to %s",
            api_base,
        )
        return AzureProvider(
            model=model,
            api_base=api_base,
            embed_model=embed_model,
        )
    else:
        raise ValueError(
            f"Unknown provider: {provider!r}. "
            f"Valid providers: 'ollama', 'openai', 'azure'"
        )
