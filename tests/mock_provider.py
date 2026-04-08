"""Shared mock provider for Sentinel tests."""

from __future__ import annotations

import json

from sentinel.core.provider import LLMResponse


class MockProvider:
    """A mock ModelProvider for testing. Configurable responses."""

    def __init__(
        self,
        *,
        generate_text: str = "",
        generate_token_count: int | None = 50,
        generate_duration_ms: float | None = 100.0,
        embed_result: list[list[float]] | None = None,
        health: bool = True,
        generate_error: Exception | None = None,
    ) -> None:
        self.model = "test-model"
        self.embed_model = "test-embed"
        self._generate_text = generate_text
        self._generate_token_count = generate_token_count
        self._generate_duration_ms = generate_duration_ms
        self._embed_result = embed_result
        self._health = health
        self._generate_error = generate_error
        self.generate_calls: list[dict] = []
        self.embed_calls: list[list[str]] = []
        self.health_calls: int = 0

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
        self.generate_calls.append({
            "prompt": prompt,
            "system": system,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "num_ctx": num_ctx,
            "json_output": json_output,
        })
        if self._generate_error:
            raise self._generate_error
        return LLMResponse(
            text=self._generate_text,
            token_count=self._generate_token_count,
            duration_ms=self._generate_duration_ms,
        )

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        self.embed_calls.append(texts)
        return self._embed_result

    def check_health(self) -> bool:
        self.health_calls += 1
        return self._health


def make_mock_provider(**kwargs) -> MockProvider:
    """Create a MockProvider with the given configuration."""
    return MockProvider(**kwargs)


def make_judge_provider(
    *,
    is_real: bool = True,
    adjusted_severity: str = "medium",
    summary: str = "Test summary",
    reasoning: str = "Test reasoning",
    token_count: int = 55,
    duration_ms: float = 1200.0,
    health: bool = True,
    error: Exception | None = None,
) -> MockProvider:
    """Create a MockProvider configured for judge tests."""
    response = json.dumps({
        "is_real": is_real,
        "adjusted_severity": adjusted_severity,
        "summary": summary,
        "reasoning": reasoning,
    })
    return MockProvider(
        generate_text=response,
        generate_token_count=token_count,
        generate_duration_ms=duration_ms,
        health=health,
        generate_error=error,
    )
