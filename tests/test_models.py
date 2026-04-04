"""Tests for Sentinel data models."""

from datetime import datetime, timezone

import pytest

from sentinel.models import (
    DetectorContext,
    Evidence,
    EvidenceType,
    Finding,
    FindingStatus,
    RunSummary,
    ScopeType,
    Severity,
)


class TestEvidence:
    def test_create_evidence(self):
        e = Evidence(
            type=EvidenceType.CODE,
            source="src/main.py",
            content="# TODO: fix this",
            line_range=(10, 10),
        )
        assert e.type == EvidenceType.CODE
        assert e.source == "src/main.py"
        assert e.line_range == (10, 10)

    def test_to_dict(self):
        e = Evidence(type=EvidenceType.LINT_OUTPUT, source="ruff", content="E501")
        d = e.to_dict()
        assert d["type"] == "lint_output"
        assert d["source"] == "ruff"
        assert d["line_range"] is None

    def test_from_dict(self):
        data = {
            "type": "git_history",
            "source": "blame",
            "content": "commit abc",
            "line_range": [5, 10],
        }
        e = Evidence.from_dict(data)
        assert e.type == EvidenceType.GIT_HISTORY
        assert e.line_range == (5, 10)

    def test_from_dict_no_line_range(self):
        data = {"type": "code", "source": "file.py", "content": "x = 1"}
        e = Evidence.from_dict(data)
        assert e.line_range is None

    def test_evidence_is_frozen(self):
        e = Evidence(type=EvidenceType.CODE, source="x", content="y")
        with pytest.raises(AttributeError):
            e.source = "z"  # type: ignore[misc]


class TestFinding:
    def _make_finding(self, **kwargs):
        defaults = {
            "detector": "test-detector",
            "category": "code-quality",
            "severity": Severity.MEDIUM,
            "confidence": 0.8,
            "title": "Test finding",
            "description": "A test finding",
            "evidence": [
                Evidence(type=EvidenceType.CODE, source="x.py", content="bad code")
            ],
        }
        defaults.update(kwargs)
        return Finding(**defaults)

    def test_create_finding(self):
        f = self._make_finding()
        assert f.detector == "test-detector"
        assert f.status == FindingStatus.NEW
        assert f.fingerprint == ""

    def test_confidence_validation(self):
        with pytest.raises(ValueError, match="confidence must be 0.0–1.0"):
            self._make_finding(confidence=1.5)

    def test_confidence_lower_bound(self):
        with pytest.raises(ValueError, match="confidence must be 0.0–1.0"):
            self._make_finding(confidence=-0.1)

    def test_confidence_boundaries(self):
        f0 = self._make_finding(confidence=0.0)
        f1 = self._make_finding(confidence=1.0)
        assert f0.confidence == 0.0
        assert f1.confidence == 1.0

    def test_severity_coercion(self):
        f = self._make_finding(severity="high")
        assert f.severity == Severity.HIGH

    def test_to_dict(self):
        f = self._make_finding(file_path="x.py", line_start=10)
        d = f.to_dict()
        assert d["severity"] == "medium"
        assert d["status"] == "new"
        assert isinstance(d["evidence"], list)
        assert d["evidence"][0]["type"] == "code"

    def test_evidence_json(self):
        f = self._make_finding()
        j = f.evidence_json()
        assert '"type": "code"' in j

    def test_context_json_none(self):
        f = self._make_finding()
        assert f.context_json() is None

    def test_context_json_with_data(self):
        f = self._make_finding(context={"key": "value"})
        assert '"key": "value"' in f.context_json()

    def test_timestamp_auto(self):
        f = self._make_finding()
        assert isinstance(f.timestamp, datetime)
        assert f.timestamp.tzinfo == timezone.utc


class TestDetectorContext:
    def test_defaults(self):
        ctx = DetectorContext(repo_root="/tmp/repo")
        assert ctx.scope == ScopeType.FULL
        assert ctx.changed_files is None
        assert ctx.config == {}

    def test_incremental(self):
        ctx = DetectorContext(
            repo_root="/tmp/repo",
            scope=ScopeType.INCREMENTAL,
            changed_files=["a.py", "b.py"],
        )
        assert ctx.scope == ScopeType.INCREMENTAL
        assert len(ctx.changed_files) == 2


class TestRunSummary:
    def test_defaults(self):
        r = RunSummary(repo_path="/tmp/repo")
        assert r.id is None
        assert r.scope == ScopeType.FULL
        assert r.finding_count == 0
        assert isinstance(r.started_at, datetime)
