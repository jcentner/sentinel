"""Tests for async provider helpers (ADR-017)."""

from __future__ import annotations

import asyncio

import pytest

from sentinel.core.provider import LLMResponse, aembed, agenerate


class _SyncOnlyProvider:
    """A provider with only sync methods (simulates third-party plugin)."""

    def __init__(self) -> None:
        self.model = "sync-only"
        self.calls: list[str] = []

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
        self.calls.append(prompt)
        return LLMResponse(text=f"sync:{prompt}", token_count=10, duration_ms=1.0)

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        return [[0.1] * 3 for _ in texts]

    def check_health(self) -> bool:
        return True


class _AsyncProvider:
    """A provider with native async methods."""

    def __init__(self) -> None:
        self.model = "async-native"
        self.sync_calls: list[str] = []
        self.async_calls: list[str] = []

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
        self.sync_calls.append(prompt)
        return LLMResponse(text=f"sync:{prompt}", token_count=10, duration_ms=1.0)

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
        self.async_calls.append(prompt)
        return LLMResponse(text=f"async:{prompt}", token_count=10, duration_ms=1.0)

    async def aembed(self, texts: list[str]) -> list[list[float]] | None:
        return [[0.2] * 3 for _ in texts]

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        return [[0.1] * 3 for _ in texts]

    def check_health(self) -> bool:
        return True


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


def test_agenerate_uses_native_async():
    """When provider has agenerate(), it should be called directly."""
    provider = _AsyncProvider()
    result = _run(agenerate(provider, "hello"))
    assert result.text == "async:hello"
    assert provider.async_calls == ["hello"]
    assert provider.sync_calls == []


def test_agenerate_falls_back_to_thread_pool():
    """When provider lacks agenerate(), generate() runs in thread pool."""
    provider = _SyncOnlyProvider()
    result = _run(agenerate(provider, "hello"))
    assert result.text == "sync:hello"
    assert provider.calls == ["hello"]


def test_agenerate_passes_kwargs():
    """All keyword arguments should reach the provider."""
    provider = _AsyncProvider()
    _run(agenerate(
        provider, "test",
        system="sys", temperature=0.5, max_tokens=100,
        num_ctx=4096, json_output=True,
    ))
    assert len(provider.async_calls) == 1


def test_aembed_uses_native_async():
    """When provider has aembed(), it should be called directly."""
    provider = _AsyncProvider()
    result = _run(aembed(provider, ["hello"]))
    assert result == [[0.2] * 3]


def test_aembed_falls_back_to_thread_pool():
    """When provider lacks aembed(), embed() runs in thread pool."""
    provider = _SyncOnlyProvider()
    result = _run(aembed(provider, ["hello"]))
    assert result == [[0.1] * 3]


def test_concurrent_agenerate():
    """Multiple concurrent agenerate calls should all complete."""
    async def _go():
        provider = _AsyncProvider()
        results = await asyncio.gather(
            agenerate(provider, "a"),
            agenerate(provider, "b"),
            agenerate(provider, "c"),
        )
        assert len(results) == 3
        assert {r.text for r in results} == {"async:a", "async:b", "async:c"}
        assert set(provider.async_calls) == {"a", "b", "c"}
    _run(_go())


def test_mock_provider_agenerate():
    """MockProvider should support agenerate()."""
    from tests.mock_provider import make_judge_provider

    provider = make_judge_provider(is_real=True, summary="async test")
    result = _run(agenerate(provider, "test prompt"))
    assert "is_real" in result.text
    assert len(provider.generate_calls) == 1
