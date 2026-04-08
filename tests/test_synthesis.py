"""Tests for finding cluster synthesis."""

from __future__ import annotations

import json

from sentinel.core.synthesis import (
    _build_synthesis_prompt,
    _parse_synthesis,
    synthesize_clusters,
)
from sentinel.models import (
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)


def _make_finding(title: str, detector: str = "docs-drift", fingerprint: str = "") -> Finding:
    return Finding(
        detector=detector,
        category="docs-drift",
        severity=Severity.MEDIUM,
        confidence=0.8,
        title=title,
        description="Test finding",
        evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="bad")],
        file_path="README.md",
        fingerprint=fingerprint,
    )


class TestParseSynthesis:
    def test_parses_valid_json(self):
        text = json.dumps({
            "root_cause": "README CLI section outdated",
            "recommended_action": "Rewrite CLI section",
            "redundant_fingerprints": ["abc123"],
            "confidence": 0.85,
        })
        result = _parse_synthesis(text)
        assert result is not None
        assert result.root_cause == "README CLI section outdated"
        assert result.recommended_action == "Rewrite CLI section"
        assert result.redundant_fingerprints == ["abc123"]
        assert result.confidence == 0.85

    def test_parses_json_in_code_fence(self):
        text = '```json\n{"root_cause": "test", "recommended_action": "fix"}\n```'
        result = _parse_synthesis(text)
        assert result is not None
        assert result.root_cause == "test"

    def test_returns_none_for_empty(self):
        assert _parse_synthesis("") is None
        assert _parse_synthesis("no json here") is None

    def test_returns_none_without_root_cause(self):
        result = _parse_synthesis('{"recommended_action": "fix"}')
        assert result is None

    def test_defaults_for_missing_fields(self):
        result = _parse_synthesis('{"root_cause": "test"}')
        assert result is not None
        assert result.recommended_action == ""
        assert result.redundant_fingerprints == []
        assert result.confidence == 0.7

    def test_non_numeric_confidence_defaults(self):
        result = _parse_synthesis('{"root_cause": "test", "confidence": "high"}')
        assert result is not None
        assert result.confidence == 0.7

    def test_non_list_redundant_fingerprints_defaults(self):
        result = _parse_synthesis('{"root_cause": "test", "redundant_fingerprints": "fp1, fp2"}')
        assert result is not None
        assert result.redundant_fingerprints == []


class TestBuildSynthesisPrompt:
    def test_includes_findings(self):
        findings = [
            _make_finding("Stale link in `/api/foo`", fingerprint="fp1"),
            _make_finding("Stale link in `/api/bar`", fingerprint="fp2"),
            _make_finding("Stale link in `/api/baz`", fingerprint="fp3"),
        ]
        prompt = _build_synthesis_prompt(findings, "docs-drift: Stale link")
        assert "Stale link" in prompt
        assert "fp1" in prompt
        assert "root_cause" in prompt

    def test_truncates_evidence(self):
        long_evidence = "x" * 500
        f = Finding(
            detector="docs-drift", category="docs-drift",
            severity=Severity.MEDIUM, confidence=0.8,
            title="Long evidence", description="test",
            evidence=[Evidence(type=EvidenceType.CODE, source="big.py", content=long_evidence)],
        )
        prompt = _build_synthesis_prompt([f], "test")
        # Evidence should be truncated to 300 chars
        assert len(prompt) < len(long_evidence) + 500


class TestSynthesizeClusters:
    def test_empty_findings(self):
        result = synthesize_clusters(
            [], provider=_MockProvider(), min_cluster_size=3,
        )
        assert result == []

    def test_no_clusters_passes_through(self):
        """Findings that don't form clusters pass through unchanged."""
        findings = [_make_finding(f"Unique finding {i}") for i in range(2)]
        result = synthesize_clusters(
            findings, provider=_MockProvider(), min_cluster_size=3,
        )
        assert len(result) == 2

    def test_cluster_gets_synthesized(self):
        """A cluster of 3+ findings gets synthesis annotations."""
        findings = [
            _make_finding("Stale link in `/api/foo`", fingerprint="fp1"),
            _make_finding("Stale link in `/api/bar`", fingerprint="fp2"),
            _make_finding("Stale link in `/api/baz`", fingerprint="fp3"),
        ]
        provider = _MockProvider(response=json.dumps({
            "root_cause": "API docs section outdated",
            "recommended_action": "Update API docs",
            "redundant_fingerprints": ["fp2"],
            "confidence": 0.9,
        }))
        result = synthesize_clusters(
            findings, provider=provider, min_cluster_size=3,
        )
        assert len(result) == 3
        # All findings should have synthesis context
        for f in result:
            assert f.context is not None
            assert "synthesis" in f.context
            assert f.context["synthesis"]["root_cause"] == "API docs section outdated"

        # fp2 should be marked redundant
        fp2_finding = next(f for f in result if f.fingerprint == "fp2")
        assert fp2_finding.context["synthesis"]["redundant"] is True

        # fp1 and fp3 should not be redundant
        fp1_finding = next(f for f in result if f.fingerprint == "fp1")
        assert "redundant" not in fp1_finding.context["synthesis"]

    def test_unhealthy_provider_skips(self):
        """If provider is unhealthy, pass through unchanged."""
        findings = [_make_finding("test")] * 5
        provider = _MockProvider(healthy=False)
        result = synthesize_clusters(
            findings, provider=provider, min_cluster_size=3,
        )
        assert len(result) == 5
        for f in result:
            assert f.context is None or "synthesis" not in (f.context or {})

    def test_llm_failure_passes_through(self):
        """If LLM call fails, findings pass through unchanged."""
        findings = [
            _make_finding("Stale link in `/api/foo`"),
            _make_finding("Stale link in `/api/bar`"),
            _make_finding("Stale link in `/api/baz`"),
        ]
        provider = _MockProvider(fail=True)
        result = synthesize_clusters(
            findings, provider=provider, min_cluster_size=3,
        )
        assert len(result) == 3
        for f in result:
            assert f.context is None or "synthesis" not in (f.context or {})


class _MockProvider:
    """Mock ModelProvider for synthesis tests."""

    def __init__(self, response: str = '{"root_cause": "test"}', healthy: bool = True, fail: bool = False):
        self._response = response
        self._healthy = healthy
        self._fail = fail

    def check_health(self) -> bool:
        return self._healthy

    def generate(self, prompt, **kwargs):
        if self._fail:
            raise RuntimeError("LLM unavailable")
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.text = self._response
        resp.token_count = 100
        resp.duration_ms = 50.0
        return resp

    def __str__(self):
        return "mock-provider"
