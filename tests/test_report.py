"""Tests for the morning report generator."""

from __future__ import annotations

from sentinel.core.report import generate_report
from sentinel.models import (
    Evidence,
    EvidenceType,
    Finding,
    RunSummary,
    ScopeType,
    Severity,
)


def _make_finding(severity=Severity.MEDIUM, **kwargs) -> Finding:
    defaults = {
        "detector": "test",
        "category": "code-quality",
        "severity": severity,
        "confidence": 0.8,
        "title": "Test finding",
        "description": "Something wrong",
        "evidence": [Evidence(type=EvidenceType.CODE, source="x.py", content="bad")],
        "file_path": "src/x.py",
        "line_start": 10,
    }
    defaults.update(kwargs)
    return Finding(**defaults)


def _make_run() -> RunSummary:
    return RunSummary(id=1, repo_path="/tmp/test-repo", scope=ScopeType.FULL)


class TestReportGeneration:
    def test_empty_report(self):
        report = generate_report([], _make_run())
        assert "No issues found" in report
        assert "Sentinel Morning Report" in report

    def test_report_with_findings(self):
        findings = [
            _make_finding(severity=Severity.HIGH, title="High issue"),
            _make_finding(severity=Severity.LOW, title="Low issue"),
        ]
        report = generate_report(findings, _make_run())
        assert "High issue" in report
        assert "Low issue" in report
        assert "**Findings**: 2" in report
        # New/recurring stats
        assert "**New**: 2" in report
        assert "**Recurring**: 0" in report

    def test_severity_summary(self):
        findings = [
            _make_finding(severity=Severity.HIGH),
            _make_finding(severity=Severity.HIGH, title="Another high"),
            _make_finding(severity=Severity.LOW),
        ]
        report = generate_report(findings, _make_run())
        assert "**HIGH**: 2" in report
        assert "**LOW**: 1" in report

    def test_grouped_by_severity(self):
        findings = [
            _make_finding(severity=Severity.CRITICAL, title="Critical"),
            _make_finding(severity=Severity.LOW, title="Minor"),
        ]
        report = generate_report(findings, _make_run())
        # Critical should appear before Low
        crit_pos = report.index("CRITICAL")
        low_pos = report.index("LOW")
        assert crit_pos < low_pos

    def test_evidence_in_details_block(self):
        report = generate_report([_make_finding()], _make_run())
        assert "<details>" in report
        assert "Evidence" in report

    def test_recurring_marker(self):
        f = _make_finding(context={"occurrence_count": 3, "recurring": True})
        report = generate_report([f], _make_run())
        assert "♻️" in report
        assert "×3" in report
        # Recurring count in summary
        assert "**Recurring**: 1" in report

    def test_fp_marker(self):
        f = _make_finding(context={"judge_verdict": "likely_false_positive"})
        report = generate_report([f], _make_run())
        assert "FP?" in report

    def test_judge_summary(self):
        f = _make_finding(
            context={"judge": {"summary": "This is a real issue"}}
        )
        report = generate_report([f], _make_run())
        assert "This is a real issue" in report

    def test_write_to_file(self, tmp_path):
        out = tmp_path / "report.md"
        report = generate_report([_make_finding()], _make_run(), output_path=out)
        assert out.exists()
        assert out.read_text() == report

    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "subdir" / "report.md"
        generate_report([], _make_run(), output_path=out)
        assert out.exists()

    def test_repo_path_in_header(self):
        report = generate_report([], _make_run())
        assert "/tmp/test-repo" in report

    def test_confidence_percentage(self):
        f = _make_finding(confidence=0.73)
        report = generate_report([f], _make_run())
        assert "73%" in report

    def test_actions_section(self):
        report = generate_report([_make_finding()], _make_run())
        assert "sentinel suppress" in report
        assert "sentinel approve" in report
        assert "sentinel history" in report

    def test_version_from_package(self):
        from sentinel import __version__
        report = generate_report([_make_finding()], _make_run())
        assert f"v{__version__}" in report

    def test_finding_shows_fingerprint_id(self):
        f = _make_finding(fingerprint="abc123def456")
        report = generate_report([f], _make_run())
        assert "[abc123def456]" in report

    def test_finding_without_fingerprint_ok(self):
        f = _make_finding()
        report = generate_report([f], _make_run())
        # Should not crash, just no ID shown
        assert "Test finding" in report

    def test_low_findings_truncated_when_exceeding_cap(self):
        """Reports should truncate LOW findings to keep the report scannable."""
        from sentinel.core.report import _MAX_LOW_FINDINGS

        # Create more LOW findings than the cap, each in a unique directory
        # so they don't cluster together
        lows = [
            _make_finding(
                severity=Severity.LOW,
                title=f"Low issue {i}",
                file_path=f"dir{i}/x.py",
            )
            for i in range(_MAX_LOW_FINDINGS + 10)
        ]
        report = generate_report(lows, _make_run())

        # Should show exactly _MAX_LOW_FINDINGS, not all
        assert f"Low issue {_MAX_LOW_FINDINGS - 1}" in report
        assert f"Low issue {_MAX_LOW_FINDINGS + 5}" not in report
        assert "more LOW findings not shown" in report

    def test_medium_findings_not_truncated(self):
        """MEDIUM+ findings must all be shown regardless of count."""
        mediums = [
            _make_finding(severity=Severity.MEDIUM, title=f"Medium issue {i}")
            for i in range(50)
        ]
        report = generate_report(mediums, _make_run())
        # All 50 should be in the report
        assert "Medium issue 49" in report
        assert "not shown" not in report

    def test_detector_breakdown_in_summary(self):
        """Multiple detectors should show a per-detector count."""
        findings = [
            _make_finding(detector="docs-drift", title="Link broken"),
            _make_finding(detector="docs-drift", title="Another link"),
            _make_finding(detector="git-hotspots", title="Hot file"),
        ]
        report = generate_report(findings, _make_run())
        assert "docs-drift (2)" in report
        assert "git-hotspots (1)" in report
