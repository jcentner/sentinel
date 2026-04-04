"""Tests for the lint runner detector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sentinel.detectors.lint_runner import LintRunner
from sentinel.models import DetectorContext, DetectorTier, Severity, ScopeType


@pytest.fixture
def runner():
    return LintRunner()


@pytest.fixture
def repo_with_lint_errors(tmp_path):
    """Create a temp repo with Python files that will trigger ruff errors."""
    (tmp_path / "bad.py").write_text("import os\nimport sys\nx=1\n")
    (tmp_path / "clean.py").write_text("x = 1\n")
    return tmp_path


SAMPLE_RUFF_OUTPUT = json.dumps([
    {
        "code": "F401",
        "message": "`os` imported but unused",
        "filename": "/tmp/repo/bad.py",
        "location": {"row": 1, "column": 1},
        "end_location": {"row": 1, "column": 10},
        "fix": {"message": "Remove unused import: `os`", "edits": [], "applicability": "safe"},
        "url": "https://docs.astral.sh/ruff/rules/unused-import",
    },
    {
        "code": "E501",
        "message": "Line too long (120 > 88)",
        "filename": "/tmp/repo/bad.py",
        "location": {"row": 3, "column": 89},
        "end_location": {"row": 3, "column": 120},
        "fix": None,
        "url": None,
    },
])


class TestLintRunner:
    def test_properties(self, runner):
        assert runner.name == "lint-runner"
        assert runner.tier == DetectorTier.DETERMINISTIC
        assert "code-quality" in runner.categories

    @patch("sentinel.detectors.lint_runner.subprocess.run")
    def test_parses_ruff_output(self, mock_run, runner):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=SAMPLE_RUFF_OUTPUT,
            stderr="",
        )
        ctx = DetectorContext(repo_root="/tmp/repo")
        findings = runner.detect(ctx)
        assert len(findings) == 2
        assert findings[0].title == "F401: `os` imported but unused"
        assert findings[0].severity == Severity.HIGH  # F-codes are high
        assert findings[1].severity == Severity.MEDIUM  # E-codes are medium

    @patch("sentinel.detectors.lint_runner.subprocess.run")
    def test_clean_repo(self, mock_run, runner):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr="",
        )
        ctx = DetectorContext(repo_root="/tmp/repo")
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.lint_runner.subprocess.run")
    def test_ruff_not_installed(self, mock_run, runner):
        mock_run.side_effect = FileNotFoundError("ruff not found")
        ctx = DetectorContext(repo_root="/tmp/repo")
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.lint_runner.subprocess.run")
    def test_evidence_fields(self, mock_run, runner):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=SAMPLE_RUFF_OUTPUT,
            stderr="",
        )
        ctx = DetectorContext(repo_root="/tmp/repo")
        findings = runner.detect(ctx)
        f = findings[0]
        assert f.detector == "lint-runner"
        assert f.category == "code-quality"
        assert f.confidence == 1.0
        assert len(f.evidence) == 1
        assert f.evidence[0].type.value == "lint_output"

    @patch("sentinel.detectors.lint_runner.subprocess.run")
    def test_incremental_scope(self, mock_run, runner, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["a.py"],
        )
        runner.detect(ctx)
        cmd = mock_run.call_args[0][0]
        assert "a.py" in cmd

    @patch("sentinel.detectors.lint_runner.subprocess.run")
    def test_invalid_json(self, mock_run, runner):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="not json",
            stderr="",
        )
        ctx = DetectorContext(repo_root="/tmp/repo")
        findings = runner.detect(ctx)
        assert findings == []

    def test_real_ruff_on_dirty_file(self, runner, tmp_path):
        """Integration test: actually run ruff on a file with issues."""
        (tmp_path / "dirty.py").write_text("import os\nimport sys\nx=1\n")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = runner.detect(ctx)
        # ruff should find at least the unused imports
        assert len(findings) >= 1
        assert all(f.detector == "lint-runner" for f in findings)
