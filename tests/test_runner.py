"""Tests for the pipeline runner."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sentinel.core.runner import run_scan
from sentinel.detectors.base import Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)
from sentinel.store.db import get_connection


class _MockDetector(Detector):
    """A mock detector that returns canned findings."""

    def __init__(self, findings: list[Finding] | None = None):
        self._findings = findings or []

    @property
    def name(self) -> str:
        return "mock-detector"

    @property
    def description(self) -> str:
        return "Mock"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["test"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        return self._findings


class _FailingDetector(Detector):
    """A detector that always raises."""

    @property
    def name(self) -> str:
        return "failing-detector"

    @property
    def description(self) -> str:
        return "Fails"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["test"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        raise RuntimeError("Intentional failure")


def _sample_finding(title: str = "Test finding") -> Finding:
    return Finding(
        detector="mock-detector",
        category="test",
        severity=Severity.MEDIUM,
        confidence=0.8,
        title=title,
        description="A test finding",
        evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="bad")],
        file_path="x.py",
        line_start=1,
    )


@pytest.fixture
def db_conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = get_connection(Path(tmpdir) / "test.db")
        yield conn
        conn.close()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "x.py").write_text("# some code\n")
    return tmp_path


class TestRunner:
    def test_full_pipeline(self, db_conn, repo):
        detector = _MockDetector([_sample_finding()])
        run, findings, report = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        assert run.id is not None
        assert len(findings) == 1
        assert "Test finding" in report

    def test_empty_findings(self, db_conn, repo):
        detector = _MockDetector([])
        _run, findings, report = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        assert len(findings) == 0
        assert "No issues found" in report

    def test_failing_detector_isolated(self, db_conn, repo):
        """A failing detector should not abort the run."""
        good = _MockDetector([_sample_finding()])
        bad = _FailingDetector()
        _run, findings, _report = run_scan(
            str(repo), db_conn,
            detectors=[bad, good],
            skip_judge=True,
        )
        assert len(findings) == 1  # Good detector's findings survive

    def test_deduplication_across_runs(self, db_conn, repo):
        detector = _MockDetector([_sample_finding()])

        # First run
        _run1, _findings1, _ = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )

        # Second run — same finding should be marked recurring
        _run2, findings2, _ = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        assert len(findings2) == 1
        assert findings2[0].context.get("recurring") is True

    def test_report_written_to_disk(self, db_conn, repo, tmp_path):
        out = tmp_path / "output" / "report.md"
        detector = _MockDetector([_sample_finding()])
        run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
            output_path=str(out),
        )
        assert out.exists()

    def test_run_record_completed(self, db_conn, repo):
        detector = _MockDetector([_sample_finding()])
        run, _, _ = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        from sentinel.store.runs import get_run_by_id
        updated = get_run_by_id(db_conn, run.id)
        assert updated.completed_at is not None
        assert updated.finding_count == 1

    def test_targeted_scan(self, db_conn, repo):
        """Targeted scan passes target_paths to detectors and uses TARGETED scope."""
        from sentinel.models import ScopeType

        captured_ctx = {}

        class _CapturingDetector(_MockDetector):
            def detect(self, context: DetectorContext) -> list[Finding]:
                captured_ctx["scope"] = context.scope
                captured_ctx["target_paths"] = context.target_paths
                return super().detect(context)

        detector = _CapturingDetector([_sample_finding()])
        run, findings, _report = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
            scope=ScopeType.TARGETED,
            target_paths=["x.py"],
        )
        assert run.id is not None
        assert len(findings) == 1
        assert captured_ctx["scope"] == ScopeType.TARGETED
        assert captured_ctx["target_paths"] == ["x.py"]
