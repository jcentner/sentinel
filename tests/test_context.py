"""Tests for the context gatherer."""

from __future__ import annotations

import pytest

from sentinel.core.context import gather_context
from sentinel.models import EvidenceType, Finding, Severity


def _make_finding(**kwargs) -> Finding:
    defaults = {
        "detector": "test",
        "category": "code-quality",
        "severity": Severity.MEDIUM,
        "confidence": 0.8,
        "title": "Test issue",
        "description": "Something",
        "evidence": [],
        "file_path": "src/main.py",
        "line_start": 3,
    }
    defaults.update(kwargs)
    return Finding(**defaults)


@pytest.fixture
def repo(tmp_path):
    """Create a repo structure for context testing."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "line 1\nline 2\nline 3\nline 4\nline 5\n"
        "line 6\nline 7\nline 8\nline 9\nline 10\n"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text(
        "def test_main():\n    pass\n"
    )
    return tmp_path


class TestContextGatherer:
    def test_adds_surrounding_code(self, repo):
        f = _make_finding(file_path="src/main.py", line_start=5)
        gather_context([f], str(repo))
        code_evidence = [e for e in f.evidence if e.type == EvidenceType.CODE]
        assert len(code_evidence) >= 1
        # Should contain surrounding lines
        assert "line 5" in code_evidence[0].content

    def test_adds_related_test_file(self, repo):
        f = _make_finding(file_path="src/main.py", line_start=3)
        gather_context([f], str(repo))
        test_evidence = [e for e in f.evidence if e.type == EvidenceType.TEST]
        assert len(test_evidence) == 1
        assert "test_main" in test_evidence[0].content

    def test_handles_missing_file(self, repo):
        f = _make_finding(file_path="src/nonexistent.py", line_start=1)
        gather_context([f], str(repo))
        # Should not crash, just not add code context
        code_evidence = [e for e in f.evidence if e.type == EvidenceType.CODE]
        assert len(code_evidence) == 0

    def test_handles_no_file_path(self, repo):
        f = _make_finding(file_path=None, line_start=None)
        initial_evidence_count = len(f.evidence)
        gather_context([f], str(repo))
        assert len(f.evidence) == initial_evidence_count

    def test_no_test_file(self, repo):
        (repo / "src" / "orphan.py").write_text("x = 1\n")
        f = _make_finding(file_path="src/orphan.py", line_start=1)
        gather_context([f], str(repo))
        test_evidence = [e for e in f.evidence if e.type == EvidenceType.TEST]
        assert len(test_evidence) == 0

    def test_context_around_first_line(self, repo):
        f = _make_finding(file_path="src/main.py", line_start=1)
        gather_context([f], str(repo))
        code_evidence = [e for e in f.evidence if e.type == EvidenceType.CODE]
        assert len(code_evidence) >= 1
        assert "line 1" in code_evidence[0].content

    def test_multiple_findings(self, repo):
        findings = [
            _make_finding(file_path="src/main.py", line_start=2),
            _make_finding(file_path="src/main.py", line_start=8),
        ]
        gather_context(findings, str(repo))
        for f in findings:
            assert len(f.evidence) >= 1
