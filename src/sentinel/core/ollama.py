"""Shared Ollama utilities — connection check and LLM API call."""

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
