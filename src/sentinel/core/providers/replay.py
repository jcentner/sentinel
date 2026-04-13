"""Replay and recording providers for deterministic eval and prompt testing."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from sentinel.core.provider import LLMResponse, ModelProvider, agenerate

logger = logging.getLogger(__name__)

# Default judge response used when no recording matches.
_DEFAULT_JUDGE_RESPONSE = json.dumps({
    "is_real": True,
    "adjusted_severity": "medium",
    "summary": "Replay default — no matching recording",
    "reasoning": "No recorded response for this prompt hash; defaulting to confirmed.",
})


def _prompt_hash(prompt: str) -> str:
    """Compute a stable hash of a prompt for replay matching."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


class ReplayProvider:
    """Returns pre-recorded LLM responses matched by prompt hash.

    Use with ``sentinel eval --full-pipeline --replay-file`` to exercise
    the judge and synthesis paths in CI without a live model.

    Matching strategy:
    1. Exact prompt-hash match against recorded responses.
    2. If no match, return *default_response* (safe default: confirm finding).

    The miss count is tracked and logged so users know how many prompts
    fell through to the default.
    """

    def __init__(
        self,
        recordings: list[dict[str, Any]],
        *,
        default_response: str = _DEFAULT_JUDGE_RESPONSE,
    ) -> None:
        self.model = "replay"
        self.embed_model = ""
        self._responses: dict[str, dict[str, Any]] = {}
        for rec in recordings:
            self._responses[rec["prompt_hash"]] = rec
        self._default_response = default_response
        self.hits = 0
        self.misses = 0
        self._calls: list[dict[str, Any]] = []

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        **kwargs: Any,
    ) -> ReplayProvider:
        """Load recordings from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        recordings = data.get("recordings", data) if isinstance(data, dict) else data
        return cls(recordings, **kwargs)

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
        h = _prompt_hash(prompt)
        self._calls.append({"prompt_hash": h, "system": system})

        rec = self._responses.get(h)
        if rec is not None:
            self.hits += 1
            return LLMResponse(
                text=rec["response"],
                token_count=rec.get("token_count", 50),
                duration_ms=rec.get("duration_ms", 0.0),
            )

        self.misses += 1
        logger.debug("Replay miss for hash %s — using default", h)
        return LLMResponse(
            text=self._default_response,
            token_count=50,
            duration_ms=0.0,
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
        """Async generate — replay is instant, no I/O."""
        return self.generate(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=num_ctx,
            json_output=json_output,
        )

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        return None

    def check_health(self) -> bool:
        return True

    @property
    def match_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class RecordingProvider:
    """Wraps a real provider and records all generate() interactions.

    Use with ``sentinel eval --full-pipeline --record-responses`` to
    capture prompt→response pairs for later replay.
    """

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider
        self.model = getattr(provider, "model", "unknown")
        self.embed_model = getattr(provider, "embed_model", "")
        self.recordings: list[dict[str, Any]] = []

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
        resp = self._provider.generate(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=num_ctx,
            json_output=json_output,
        )
        self.recordings.append({
            "prompt_hash": _prompt_hash(prompt),
            "prompt_preview": prompt[:300],
            "response": resp.text,
            "token_count": resp.token_count,
            "duration_ms": resp.duration_ms,
        })
        return resp

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
        """Async generate — delegates to wrapped provider's async path."""
        resp = await agenerate(
            self._provider,
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=num_ctx,
            json_output=json_output,
        )
        self.recordings.append({
            "prompt_hash": _prompt_hash(prompt),
            "prompt_preview": prompt[:300],
            "response": resp.text,
            "token_count": resp.token_count,
            "duration_ms": resp.duration_ms,
        })
        return resp

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        return self._provider.embed(texts)

    def check_health(self) -> bool:
        return self._provider.check_health()

    def save(self, path: str | Path) -> None:
        """Write recorded interactions to a JSON file."""
        data = {
            "model": self.model,
            "recording_count": len(self.recordings),
            "recordings": self.recordings,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved %d recordings to %s", len(self.recordings), path)
