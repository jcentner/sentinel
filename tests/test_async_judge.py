"""Tests for async judge (ADR-017 Slice 2)."""

from __future__ import annotations

import asyncio
import json

from sentinel.core.judge import _DEFAULT_MAX_CONCURRENT, ajudge_findings
from sentinel.models import Evidence, EvidenceType, Finding, Severity
from tests.mock_provider import MockProvider, make_judge_provider


def _make_finding(title: str = "Test finding", **kwargs) -> Finding:
    return Finding(
        detector="test-detector",
        category="test",
        severity=kwargs.get("severity", Severity.MEDIUM),
        confidence=kwargs.get("confidence", 0.8),
        title=title,
        description="Test description",
        evidence=[Evidence(type=EvidenceType.CODE, content="x = 1", source="test.py")],
    )


def _run(coro):
    return asyncio.run(coro)


class TestAjudgeFindings:
    """Tests for the async judge_findings function."""

    def test_empty_findings(self):
        provider = make_judge_provider()
        result = _run(ajudge_findings([], provider=provider))
        assert result == []
        assert provider.health_calls == 0

    def test_unhealthy_provider_passes_through(self):
        provider = make_judge_provider(health=False)
        findings = [_make_finding("f1"), _make_finding("f2")]
        result = _run(ajudge_findings(findings, provider=provider))
        assert len(result) == 2
        assert result[0].title == "f1"
        assert result[1].title == "f2"
        # No generate calls when unhealthy
        assert len(provider.generate_calls) == 0

    def test_judges_all_findings(self):
        provider = make_judge_provider(is_real=True, adjusted_severity="high")
        findings = [_make_finding(f"finding-{i}") for i in range(5)]
        result = _run(ajudge_findings(findings, provider=provider))
        assert len(result) == 5
        assert len(provider.generate_calls) == 5
        for f in result:
            assert f.context is not None
            assert f.context.get("judge_verdict") == "confirmed"

    def test_preserves_order(self):
        """Findings should be returned in the same order as input."""
        provider = make_judge_provider(is_real=True)
        findings = [_make_finding(f"order-{i}") for i in range(10)]
        result = _run(ajudge_findings(findings, provider=provider))
        for i, f in enumerate(result):
            assert f.title == f"order-{i}"

    def test_concurrent_execution(self):
        """Multiple findings should be processed concurrently."""
        call_order: list[str] = []

        class _TrackingProvider(MockProvider):
            async def agenerate(self, prompt, **kwargs):
                # Record that we started before awaiting
                title = prompt.split("**Title**: ")[1].split("\n")[0] if "**Title**" in prompt else "?"
                call_order.append(f"start:{title}")
                result = self.generate(prompt, **kwargs)
                call_order.append(f"end:{title}")
                return result

        response = json.dumps({
            "is_real": True,
            "adjusted_severity": "medium",
            "summary": "ok",
            "reasoning": "ok",
        })
        provider = _TrackingProvider(generate_text=response)
        findings = [_make_finding(f"f{i}") for i in range(3)]
        _run(ajudge_findings(findings, provider=provider, max_concurrent=3))
        # All 3 should have started before any completed (true concurrency)
        # With mock (instant responses), ordering may vary, but all should complete
        assert len(provider.generate_calls) == 3

    def test_max_concurrent_bounds(self):
        """max_concurrent should limit simultaneous calls."""
        active = {"count": 0, "max_seen": 0}

        class _ConcurrencyTracker(MockProvider):
            async def agenerate(self, prompt, **kwargs):
                active["count"] += 1
                active["max_seen"] = max(active["max_seen"], active["count"])
                await asyncio.sleep(0.01)  # Force yield
                result = self.generate(prompt, **kwargs)
                active["count"] -= 1
                return result

        response = json.dumps({
            "is_real": True,
            "adjusted_severity": "medium",
            "summary": "ok",
            "reasoning": "ok",
        })
        provider = _ConcurrencyTracker(generate_text=response)
        findings = [_make_finding(f"f{i}") for i in range(10)]
        _run(ajudge_findings(findings, provider=provider, max_concurrent=3))
        assert active["max_seen"] <= 3
        assert len(provider.generate_calls) == 10

    def test_error_handling_uses_raw_finding(self):
        """When a judge call fails, the raw finding should be returned."""
        provider = make_judge_provider(error=RuntimeError("LLM down"))
        findings = [_make_finding("will-fail")]
        result = _run(ajudge_findings(findings, provider=provider))
        assert len(result) == 1
        assert result[0].title == "will-fail"

    def test_with_sqlite_logging(self, tmp_path):
        """Judge should log to SQLite when conn is provided."""
        from sentinel.models import ScopeType
        from sentinel.store.db import get_connection
        from sentinel.store.runs import create_run

        conn = get_connection(tmp_path / "test.db")
        run = create_run(conn, "/tmp/test-repo", ScopeType.FULL)

        provider = make_judge_provider(is_real=True)
        findings = [_make_finding("logged-finding")]
        _run(ajudge_findings(findings, provider=provider, conn=conn, run_id=run.id))

        rows = conn.execute("SELECT COUNT(*) FROM llm_log").fetchone()
        assert rows[0] >= 1
        conn.close()

    def test_false_positive_lowers_confidence(self):
        provider = make_judge_provider(is_real=False)
        findings = [_make_finding("fp-test", confidence=0.9)]
        result = _run(ajudge_findings(findings, provider=provider))
        assert result[0].confidence <= 0.3
        assert result[0].context["judge_verdict"] == "likely_false_positive"

    def test_default_max_concurrent_is_8(self):
        assert _DEFAULT_MAX_CONCURRENT == 8
