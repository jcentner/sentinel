"""Ollama model provider — default provider for local inference."""

from __future__ import annotations

import logging

from sentinel.core.provider import LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0
_EMBED_TIMEOUT = 120.0


class OllamaProvider:
    """ModelProvider implementation for Ollama.

    Calls Ollama's ``/api/generate`` and ``/api/embed`` endpoints.
    This is the zero-config default — existing users need no changes.
    """

    def __init__(
        self,
        model: str = "qwen3.5:4b",
        ollama_url: str = "http://localhost:11434",
        embed_model: str = "",
    ) -> None:
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.embed_model = embed_model

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
        """Generate text via Ollama /api/generate."""
        import httpx

        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": num_ctx,
            },
        }
        if system:
            payload["system"] = system
        if json_output:
            payload["format"] = "json"

        resp = httpx.post(
            f"{self.ollama_url}/api/generate",
            json=payload,
            timeout=_DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()

        data = resp.json()
        text = data.get("response", "")
        token_count = data.get("eval_count")
        eval_duration_ns = data.get("eval_duration", 0)
        duration_ms = eval_duration_ns / 1e6 if eval_duration_ns else None

        return LLMResponse(
            text=text,
            token_count=token_count,
            duration_ms=duration_ms,
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
        """Async generate via Ollama /api/generate (ADR-017).

        Ollama handles one request at a time, so concurrent async calls
        will queue at the server. Still useful for not blocking the event
        loop while waiting.
        """
        import httpx

        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": num_ctx,
            },
        }
        if system:
            payload["system"] = system
        if json_output:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        text = data.get("response", "")
        token_count = data.get("eval_count")
        eval_duration_ns = data.get("eval_duration", 0)
        duration_ms = eval_duration_ns / 1e6 if eval_duration_ns else None

        return LLMResponse(
            text=text,
            token_count=token_count,
            duration_ms=duration_ms,
        )

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed texts via Ollama /api/embed."""
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
                f"{self.ollama_url}/api/embed",
                json={"model": self.embed_model, "input": texts},
                timeout=_EMBED_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Ollama embed returned %d: %s",
                    resp.status_code, resp.text[:200],
                )
                return None
            data = resp.json()
            embeddings: list[list[float]] | None = data.get("embeddings")
            if not embeddings or not isinstance(embeddings, list):
                logger.warning("Ollama embed response missing 'embeddings' key")
                return None
            return embeddings
        except Exception:
            logger.warning("Ollama embed call failed", exc_info=True)
            return None

    def check_health(self) -> bool:
        """Check if Ollama is reachable via /api/tags."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed — Ollama features disabled")
            return False

        try:
            resp = httpx.get(
                f"{self.ollama_url}/api/tags",
                timeout=5.0,
            )
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def __repr__(self) -> str:
        return f"OllamaProvider(model={self.model!r}, url={self.ollama_url!r})"

    # -- For isinstance checks against the Protocol --
    # OllamaProvider is a structural subtype of ModelProvider.
    # No explicit inheritance needed; the Protocol is runtime_checkable.
