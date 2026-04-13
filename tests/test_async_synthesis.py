"""Tests for async synthesis (ADR-017 Slice 3)."""

from __future__ import annotations

import asyncio
import json

import pytest

from sentinel.core.synthesis import (
    SynthesisResult,
    _DEFAULT_MAX_CONCURRENT_SYNTHESIS,
    asynthesize_clusters,
)
from sentinel.models import Evidence, EvidenceType, Finding, Severity
from tests.mock_provider import MockProvider


def _make_finding(
    title: str = "Test finding",
    detector: str = "test-detector",
    fingerprint: str | None = None,
) -> Finding:
    f = Finding(
        detector=detector,
        category="test",
        severity=Severity.MEDIUM,
        confidence=0.8,
        title=title,
        description="Test description",
        evidence=[Evidence(type=EvidenceType.CODE, content="x = 1", source="test.py")],
    )
    if fingerprint:
        f.fingerprint = fingerprint
    return f


def _synthesis_response(
    root_cause: str = "shared root",
    action: str = "fix it",
    redundant: list[str] | None = None,
) -> str:
    return json.dumps({
        "root_cause": root_cause,
        "recommended_action": action,
        "redundant_fingerprints": redundant or [],
        "confidence": 0.9,
    })


def _run(coro):
    return asyncio.run(coro)


class TestAsynthesizeClusters:
    """Tests for the async synthesize_clusters function."""

    def test_empty_findings(self):
        provider = MockProvider(generate_text=_synthesis_response(), health=True)
        result = _run(asynthesize_clusters([], provider=provider))
        assert result == []

    def test_unhealthy_provider_passes_through(self):
        provider = MockProvider(generate_text=_synthesis_response(), health=False)
        findings = [_make_finding(f"f{i}") for i in range(5)]
        result = _run(asynthesize_clusters(findings, provider=provider))
        assert len(result) == 5
        assert len(provider.generate_calls) == 0

    def test_standalone_findings_pass_through(self):
        """Findings that don't form clusters pass through unchanged."""
        provider = MockProvider(generate_text=_synthesis_response(), health=True)
        # Each finding has a different detector → won't cluster
        findings = [
            _make_finding("f1", detector="d1"),
            _make_finding("f2", detector="d2"),
        ]
        result = _run(asynthesize_clusters(
            findings, provider=provider, min_cluster_size=3,
        ))
        assert len(result) == 2
        # No LLM calls for standalone findings
        assert len(provider.generate_calls) == 0

    def test_cluster_gets_synthesized(self):
        """Findings that form a cluster should be synthesized."""
        provider = MockProvider(
            generate_text=_synthesis_response(root_cause="common issue"),
            health=True,
        )
        # 3 findings with same detector and same title → should cluster
        findings = [
            _make_finding("Same Issue", detector="complexity", fingerprint=f"fp{i}")
            for i in range(3)
        ]
        result = _run(asynthesize_clusters(
            findings, provider=provider, min_cluster_size=3,
        ))
        assert len(result) == 3
        # Should have made exactly 1 LLM call for the cluster
        assert len(provider.generate_calls) == 1
        # All findings should have synthesis context
        for f in result:
            assert f.context is not None
            assert "synthesis" in f.context
            assert f.context["synthesis"]["root_cause"] == "common issue"

    def test_max_concurrent_bounds(self):
        """max_concurrent should limit simultaneous synthesis calls."""
        active = {"count": 0, "max_seen": 0}

        class _ConcurrencyTracker(MockProvider):
            async def agenerate(self, prompt, **kwargs):
                active["count"] += 1
                active["max_seen"] = max(active["max_seen"], active["count"])
                await asyncio.sleep(0.01)
                result = self.generate(prompt, **kwargs)
                active["count"] -= 1
                return result

        provider = _ConcurrencyTracker(
            generate_text=_synthesis_response(),
            health=True,
        )
        # Create 6 distinct clusters of 3 findings each
        findings = []
        for cluster_idx in range(6):
            for i in range(3):
                findings.append(_make_finding(
                    f"Issue group {cluster_idx}",
                    detector=f"det-{cluster_idx}",
                    fingerprint=f"fp-{cluster_idx}-{i}",
                ))
        result = _run(asynthesize_clusters(
            findings, provider=provider, min_cluster_size=3, max_concurrent=2,
        ))
        assert active["max_seen"] <= 2
        assert len(provider.generate_calls) == 6  # 6 clusters

    def test_error_in_cluster_passes_through(self):
        """When synthesis fails, cluster findings pass through unmodified."""
        provider = MockProvider(
            generate_text="not json at all",
            health=True,
        )
        findings = [
            _make_finding("Same Issue", detector="complexity")
            for _ in range(3)
        ]
        result = _run(asynthesize_clusters(
            findings, provider=provider, min_cluster_size=3,
        ))
        # Findings still returned, but with default synthesis
        assert len(result) == 3

    def test_default_max_concurrent_is_4(self):
        assert _DEFAULT_MAX_CONCURRENT_SYNTHESIS == 4
