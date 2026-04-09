"""Azure AI Foundry model provider.

Uses Entra ID (Azure AD) token authentication via ``az account get-access-token``.
Supports Azure AI Foundry project endpoints with the OpenAI v1 API surface.

Endpoint format:
    https://<resource>.services.ai.azure.com/openai/v1/chat/completions

Authentication:
    Bearer token from ``az account get-access-token --resource https://cognitiveservices.azure.com``
    Tokens are cached and refreshed automatically when they expire.
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import time
from datetime import UTC, datetime

from sentinel.core.provider import LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120.0
_EMBED_TIMEOUT = 120.0
_TOKEN_RESOURCE = "https://cognitiveservices.azure.com"
# Refresh tokens 5 minutes before expiry
_TOKEN_REFRESH_MARGIN_SECONDS = 300
# Retry configuration for transient failures (TD-026)
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 1.0  # seconds
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class AzureProvider:
    """ModelProvider implementation for Azure AI Foundry.

    Uses Entra ID bearer tokens acquired via the Azure CLI.
    Targets the OpenAI v1 API surface exposed by Azure AI Foundry.
    """

    def __init__(
        self,
        model: str,
        api_base: str,
        embed_model: str = "",
    ) -> None:
        self.model = model
        # Ensure api_base ends without trailing slash
        self.api_base = api_base.rstrip("/")
        self.embed_model = embed_model
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _ensure_token(self) -> str:
        """Get a valid Entra ID token, refreshing if needed."""
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token

        logger.debug("Acquiring Azure Entra ID token via az CLI")
        try:
            result = subprocess.run(
                [
                    "az", "account", "get-access-token",
                    "--resource", _TOKEN_RESOURCE,
                    "--output", "json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"az account get-access-token failed (exit {result.returncode}): "
                    f"{result.stderr.strip()}"
                )
            data = json.loads(result.stdout)
            self._token = data["accessToken"]

            # Parse expiry — az CLI returns ISO format or epoch
            expires_on = data.get("expiresOn") or data.get("expires_on")
            if expires_on:
                if isinstance(expires_on, (int, float)):
                    self._token_expires_at = float(expires_on) - _TOKEN_REFRESH_MARGIN_SECONDS
                else:
                    # ISO format: "2026-04-08 12:00:00.000000"
                    try:
                        dt = datetime.fromisoformat(str(expires_on))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        self._token_expires_at = dt.timestamp() - _TOKEN_REFRESH_MARGIN_SECONDS
                    except (ValueError, TypeError):
                        # Fall back to 50 minute lifetime
                        self._token_expires_at = now + 3000
            else:
                self._token_expires_at = now + 3000

            logger.debug(
                "Azure token acquired, expires in %.0f seconds",
                self._token_expires_at - now + _TOKEN_REFRESH_MARGIN_SECONDS,
            )
            return self._token
        except FileNotFoundError as err:
            raise RuntimeError(
                "Azure CLI (az) not found. Install it and run 'az login' first. "
                "See https://learn.microsoft.com/cli/azure/install-azure-cli"
            ) from err
        except subprocess.TimeoutExpired as err:
            raise RuntimeError("az account get-access-token timed out after 30s") from err

    def _headers(self) -> dict[str, str]:
        token = self._ensure_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def _completions_url(self) -> str:
        """Build the chat completions URL for Azure AI Foundry v1 API."""
        base = self.api_base
        # If user gives a .services.ai.azure.com endpoint without /openai,
        # append it automatically
        if "services.ai.azure.com" in base and not base.endswith("/openai"):
            base = f"{base}/openai"
        return f"{base}/v1/chat/completions"

    def _embeddings_url(self) -> str:
        """Build the embeddings URL for Azure AI Foundry v1 API."""
        base = self.api_base
        if "services.ai.azure.com" in base and not base.endswith("/openai"):
            base = f"{base}/openai"
        return f"{base}/v1/embeddings"

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
        """Generate text via Azure AI Foundry OpenAI v1 API.

        Note: num_ctx is accepted for protocol compatibility but ignored —
        Azure manages context windows automatically.
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
            # Azure's newer models (gpt-5.x, o-series) require
            # max_completion_tokens instead of max_tokens
            "max_completion_tokens": max_tokens,
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}

        t0 = time.monotonic()
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = httpx.post(
                    self._completions_url(),
                    json=payload,
                    headers=self._headers(),
                    timeout=_DEFAULT_TIMEOUT,
                )
                if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                    retry_after = resp.headers.get("retry-after")
                    if retry_after:
                        with contextlib.suppress(ValueError):
                            wait = max(wait, float(retry_after))
                    logger.warning(
                        "Azure request returned %d, retrying in %.1fs (attempt %d/%d)",
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
                        "Azure request timed out, retrying in %.1fs (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise
            except httpx.ConnectError:
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "Azure connection failed, retrying in %.1fs (attempt %d/%d)",
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

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed texts via Azure AI Foundry OpenAI v1 embeddings API."""
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
                self._embeddings_url(),
                json={"model": self.embed_model, "input": texts},
                headers=self._headers(),
                timeout=_EMBED_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Azure embed returned %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return None
            data = resp.json()
            embeddings_data = data.get("data", [])
            if not embeddings_data:
                logger.warning("Azure embed response has no data")
                return None
            sorted_data = sorted(embeddings_data, key=lambda d: d.get("index", 0))
            return [item["embedding"] for item in sorted_data]
        except Exception:
            logger.warning("Azure embed call failed", exc_info=True)
            return None

    def check_health(self) -> bool:
        """Check if Azure AI Foundry endpoint is reachable."""
        try:
            import httpx
        except ImportError:
            return False

        try:
            # Try acquiring a token — this validates az CLI auth
            self._ensure_token()
            # Then check the endpoint itself
            resp = httpx.get(
                self.api_base,
                headers=self._headers(),
                timeout=10.0,
            )
            return resp.status_code < 500
        except Exception:
            logger.debug("Azure health check failed", exc_info=True)
            return False

    def __repr__(self) -> str:
        return (
            f"AzureProvider(model={self.model!r}, "
            f"api_base={self.api_base!r})"
        )
