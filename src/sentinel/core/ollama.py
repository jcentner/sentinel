"""Shared Ollama utilities — connection check, LLM API call, embeddings."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def check_ollama(ollama_url: str) -> bool:
    """Check if Ollama is reachable.

    Lazily imports httpx so modules that depend on Ollama can still
    be loaded even if httpx is missing (graceful degradation).
    """
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed — Ollama features disabled")
        return False

    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def embed_texts(
    texts: list[str],
    model: str,
    ollama_url: str = "http://localhost:11434",
) -> list[list[float]] | None:
    """Embed a batch of texts via Ollama's /api/embed endpoint.

    Returns a list of embedding vectors (one per input text),
    or None if the request fails for any reason.
    """
    if not texts:
        return []

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed — embedding disabled")
        return None

    try:
        resp = httpx.post(
            f"{ollama_url}/api/embed",
            json={"model": model, "input": texts},
            timeout=120.0,
        )
        if resp.status_code != 200:
            logger.warning(
                "Ollama embed returned %d: %s", resp.status_code, resp.text[:200]
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
