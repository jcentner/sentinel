"""OpenAI-compatible model provider.

Supports OpenAI direct, Azure OpenAI, vLLM, LM Studio, Together,
and any endpoint implementing the OpenAI ``/v1/chat/completions``
and ``/v1/embeddings`` API surface.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time

from sentinel.core.provider import LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0
_EMBED_TIMEOUT = 120.0
# Retry configuration for transient failures (TD-026)
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 1.0  # seconds
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class OpenAICompatibleProvider:
    """ModelProvider implementation for OpenAI-compatible APIs.

    Works with OpenAI, Azure OpenAI, vLLM, LM Studio, Together, etc.
    API keys are read from environment variables (never stored in config).
    """

    def __init__(
        self,
        model: str,
        api_base: str,
        api_key_env: str = "",
        embed_model: str = "",
    ) -> None:
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.embed_model = embed_model
        self._api_key_env = api_key_env
        self._api_key: str | None = None
        if api_key_env:
            self._api_key = os.environ.get(api_key_env)
            if not self._api_key:
                logger.warning(
                    "Environment variable %s not set — API calls will fail",
                    api_key_env,
                )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

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
        """Generate text via OpenAI-compatible /v1/chat/completions.

        Note: num_ctx is accepted for protocol compatibility but ignored —
        OpenAI-compatible APIs manage context windows automatically.
        """
        import httpx

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            # Newer OpenAI models (gpt-5.x) require max_completion_tokens;
            # older/compatible APIs use max_tokens.  We try the newer key
            # first and fall back on 400 errors.
            "max_completion_tokens": max_tokens,
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}

        t0 = time.monotonic()
        _used_legacy_max_tokens = False
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = httpx.post(
                    f"{self.api_base}/v1/chat/completions",
                    json=payload,
                    headers=self._headers(),
                    timeout=_DEFAULT_TIMEOUT,
                )
                # Fall back to max_tokens if the API rejects max_completion_tokens
                if (resp.status_code == 400
                        and not _used_legacy_max_tokens
                        and "max_completion_tokens" in resp.text):
                    payload.pop("max_completion_tokens", None)
                    payload["max_tokens"] = max_tokens
                    _used_legacy_max_tokens = True
                    continue
                if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                    # Respect Retry-After header if present
                    retry_after = resp.headers.get("retry-after")
                    if retry_after:
                        with contextlib.suppress(ValueError):
                            wait = max(wait, float(retry_after))
                    logger.warning(
                        "OpenAI request returned %d, retrying in %.1fs (attempt %d/%d)",
                        resp.status_code, wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            except httpx.TimeoutException:
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "OpenAI request timed out, retrying in %.1fs (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise
            except httpx.ConnectError:
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "OpenAI connection failed, retrying in %.1fs (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise

        elapsed_ms = (time.monotonic() - t0) * 1000

        data = resp.json()
        choices = data.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = data.get("usage", {})
        token_count = usage.get("completion_tokens")

        return LLMResponse(
            text=text,
            token_count=token_count,
            duration_ms=elapsed_ms,
        )

    async def agenerate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
        num_ctx: int = 2048,
        json_output: bool = False,
    ) -> LLMResponse:
        """Async generate via OpenAI-compatible /v1/chat/completions (ADR-017)."""
        import httpx

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}

        t0 = time.monotonic()
        _used_legacy_max_tokens = False
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    resp = await client.post(
                        f"{self.api_base}/v1/chat/completions",
                        json=payload,
                        headers=self._headers(),
                    )
                    if (resp.status_code == 400
                            and not _used_legacy_max_tokens
                            and "max_completion_tokens" in resp.text):
                        payload.pop("max_completion_tokens", None)
                        payload["max_tokens"] = max_tokens
                        _used_legacy_max_tokens = True
                        continue
                    if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                        wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                        retry_after = resp.headers.get("retry-after")
                        if retry_after:
                            with contextlib.suppress(ValueError):
                                wait = max(wait, float(retry_after))
                        logger.warning(
                            "OpenAI async request returned %d, retrying in %.1fs (attempt %d/%d)",
                            resp.status_code, wait, attempt + 1, _MAX_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    break
                except httpx.TimeoutException:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "OpenAI async request timed out, retrying in %.1fs (attempt %d/%d)",
                            wait, attempt + 1, _MAX_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise
                except httpx.ConnectError:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "OpenAI async connection failed, retrying in %.1fs (attempt %d/%d)",
                            wait, attempt + 1, _MAX_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise

        elapsed_ms = (time.monotonic() - t0) * 1000

        data = resp.json()
        choices = data.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = data.get("usage", {})
        token_count = usage.get("completion_tokens")

        return LLMResponse(
            text=text,
            token_count=token_count,
            duration_ms=elapsed_ms,
        )

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed texts via OpenAI-compatible /v1/embeddings."""
        if not texts:
            return []
        if not self.embed_model:
            logger.debug("No embed_model configured — embedding disabled")
            return None

        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed — embedding disabled")
            return None

        try:
            resp = httpx.post(
                f"{self.api_base}/v1/embeddings",
                json={"model": self.embed_model, "input": texts},
                headers=self._headers(),
                timeout=_EMBED_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.warning(
                    "OpenAI embed returned %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return None
            data = resp.json()
            embeddings_data = data.get("data", [])
            if not embeddings_data:
                logger.warning("OpenAI embed response has no data")
                return None
            # OpenAI returns [{embedding: [...], index: 0}, ...]
            # Sort by index to ensure correct ordering
            sorted_data = sorted(embeddings_data, key=lambda d: d.get("index", 0))
            return [item["embedding"] for item in sorted_data]
        except Exception:
            logger.warning("OpenAI embed call failed", exc_info=True)
            return None

    def check_health(self) -> bool:
        """Check if the API endpoint is reachable.

        Sends a lightweight GET to api_base to verify connectivity.
        """
        try:
            import httpx
        except ImportError:
            return False

        try:
            # Try a lightweight GET to the base URL
            resp = httpx.get(
                self.api_base,
                headers=self._headers(),
                timeout=5.0,
            )
            # Most OpenAI-compatible APIs return 200 or 404 at the base
            # (not a connection error), which means the server is up.
            return resp.status_code < 500
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def __repr__(self) -> str:
        return (
            f"OpenAICompatibleProvider(model={self.model!r}, "
            f"api_base={self.api_base!r})"
        )
