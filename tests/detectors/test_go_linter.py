"""Tests for the Go linter detector."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from sentinel.detectors.go_linter import GoLinter, _has_go_files
from sentinel.models import DetectorContext, DetectorTier, ScopeType, Severity


@pytest.fixture
def runner():
    return GoLinter()


SAMPLE_GOLANGCI_OUTPUT = json.dumps({
    "Issues": [
        {
            "FromLinter": "govet",
            "Text": "printf: fmt.Sprintf format %s reads arg #1, but call has 0 args",
            "Severity": "error",
            "Pos": {
                "Filename": "cmd/main.go",
                "Line": 42,
                "Column": 5,
            },
        },
        {
            "FromLinter": "unused",
            "Text": "func `helper` is unused",
            "Severity": "warning",
            "Pos": {
                "Filename": "internal/util.go",
                "Line": 15,
                "Column": 6,
            },
        },
        {
            "FromLinter": "gosec",
            "Text": "G101: Potential hardcoded credentials",
            "Severity": "warning",
            "Pos": {
                "Filename": "config/auth.go",
                "Line": 8,
                "Column": 2,
            },
        },
    ],
})


# ── Detector properties ──────────────────────────────────────────────


class TestGoLinterProperties:
    def test_name(self, runner: GoLinter) -> None:
        assert runner.name == "go-linter"

    def test_description(self, runner: GoLinter) -> None:
        assert "golangci-lint" in runner.description or "Go" in runner.description

    def test_tier(self, runner: GoLinter) -> None:
        assert runner.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, runner: GoLinter) -> None:
        assert "code-quality" in runner.categories


# ── Go file detection ────────────────────────────────────────────────


class TestHasGoFiles:
    def test_detects_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/myproject")
        assert _has_go_files(tmp_path) is True

    def test_detects_go_source_file(self, tmp_path):
        (tmp_path / "main.go").write_text("package main")
        assert _has_go_files(tmp_path) is True

    def test_skips_vendor_dir(self, tmp_path):
        vendor = tmp_path / "vendor" / "example.com"
        vendor.mkdir(parents=True)
        (vendor / "lib.go").write_text("package lib")
        assert _has_go_files(tmp_path) is False

    def test_no_go_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        assert _has_go_files(tmp_path) is False

    def test_empty_dir(self, tmp_path):
        assert _has_go_files(tmp_path) is False


# ── Output parsing ───────────────────────────────────────────────────


class TestParseOutput:
    def test_parse_issues(self, runner: GoLinter) -> None:
        findings = runner._parse_output(SAMPLE_GOLANGCI_OUTPUT, MagicMock())
        assert len(findings) == 3

    def test_severity_mapping_govet(self, runner: GoLinter) -> None:
        """govet is in HIGH_SEVERITY_LINTERS → HIGH."""
        findings = runner._parse_output(SAMPLE_GOLANGCI_OUTPUT, MagicMock())
        govet_finding = [f for f in findings if "govet" in f.title][0]
        assert govet_finding.severity == Severity.HIGH

    def test_severity_mapping_gosec(self, runner: GoLinter) -> None:
        """gosec (security linter) → HIGH."""
        findings = runner._parse_output(SAMPLE_GOLANGCI_OUTPUT, MagicMock())
        gosec_finding = [f for f in findings if "gosec" in f.title][0]
        assert gosec_finding.severity == Severity.HIGH

    def test_severity_mapping_unused(self, runner: GoLinter) -> None:
        """unused linter with warning severity → LOW."""
        findings = runner._parse_output(SAMPLE_GOLANGCI_OUTPUT, MagicMock())
        unused_finding = [f for f in findings if "unused" in f.title][0]
        assert unused_finding.severity == Severity.LOW

    def test_finding_metadata(self, runner: GoLinter) -> None:
        """Findings have correct file paths and line numbers."""
        findings = runner._parse_output(SAMPLE_GOLANGCI_OUTPUT, MagicMock())
        govet_finding = [f for f in findings if "govet" in f.title][0]
        assert govet_finding.file_path == "cmd/main.go"
        assert govet_finding.line_start == 42
        assert govet_finding.detector == "go-linter"
        assert govet_finding.category == "code-quality"
        assert govet_finding.confidence == 1.0
        assert len(govet_finding.evidence) == 1
        assert govet_finding.context == {"linter": "govet", "tool": "golangci-lint"}

    def test_empty_output(self, runner: GoLinter) -> None:
        assert runner._parse_output("", MagicMock()) == []

    def test_invalid_json(self, runner: GoLinter) -> None:
        assert runner._parse_output("not json", MagicMock()) == []

    def test_no_issues(self, runner: GoLinter) -> None:
        data = json.dumps({"Issues": []})
        assert runner._parse_output(data, MagicMock()) == []

    def test_null_issues(self, runner: GoLinter) -> None:
        data = json.dumps({"Issues": None})
        assert runner._parse_output(data, MagicMock()) == []


# ── Detection (with mocked subprocess) ──────────────────────────────


class TestDetection:
    def test_skips_non_go_repo(self, runner: GoLinter, tmp_path) -> None:
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.go_linter.subprocess.run")
    def test_detects_with_golangci_lint(self, mock_run, runner: GoLinter, tmp_path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/test")
        mock_run.return_value = MagicMock(stdout=SAMPLE_GOLANGCI_OUTPUT)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert len(findings) == 3
        mock_run.assert_called_once()

    @patch("sentinel.detectors.go_linter.subprocess.run", side_effect=FileNotFoundError)
    def test_no_golangci_lint_installed(self, mock_run, runner: GoLinter, tmp_path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/test")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.go_linter.subprocess.run")
    def test_timeout_handling(self, mock_run, runner: GoLinter, tmp_path) -> None:
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="golangci-lint", timeout=150)
        (tmp_path / "go.mod").write_text("module example.com/test")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert findings == []


# ── Scope filtering ──────────────────────────────────────────────────


class TestScopeFiltering:
    def test_targeted_go_file(self, runner: GoLinter, tmp_path) -> None:
        targets = runner._get_targets(
            DetectorContext(
                repo_root=str(tmp_path),
                scope=ScopeType.TARGETED,
                target_paths=["cmd/main.go"],
            ),
            tmp_path,
        )
        assert "./cmd/..." in targets

    def test_targeted_directory(self, runner: GoLinter, tmp_path) -> None:
        pkg_dir = tmp_path / "internal" / "service"
        pkg_dir.mkdir(parents=True)
        targets = runner._get_targets(
            DetectorContext(
                repo_root=str(tmp_path),
                scope=ScopeType.TARGETED,
                target_paths=[str(pkg_dir)],
            ),
            tmp_path,
        )
        assert "./internal/service/..." in targets

    def test_no_targets_returns_empty(self, runner: GoLinter, tmp_path) -> None:
        targets = runner._get_targets(
            DetectorContext(
                repo_root=str(tmp_path),
                scope=ScopeType.FULL,
            ),
            tmp_path,
        )
        assert targets == []

    def test_deduplicates(self, runner: GoLinter, tmp_path) -> None:
        targets = runner._get_targets(
            DetectorContext(
                repo_root=str(tmp_path),
                scope=ScopeType.TARGETED,
                target_paths=["cmd/main.go", "cmd/util.go"],
            ),
            tmp_path,
        )
        assert targets == ["./cmd/..."]

    def test_incremental_with_go_files(self, runner: GoLinter, tmp_path) -> None:
        targets = runner._get_targets(
            DetectorContext(
                repo_root=str(tmp_path),
                scope=ScopeType.INCREMENTAL,
                changed_files=["cmd/main.go", "internal/handler.go", "README.md"],
            ),
            tmp_path,
        )
        assert sorted(targets) == ["./cmd/...", "./internal/..."]

    def test_incremental_no_go_files(self, runner: GoLinter, tmp_path) -> None:
        targets = runner._get_targets(
            DetectorContext(
                repo_root=str(tmp_path),
                scope=ScopeType.INCREMENTAL,
                changed_files=["README.md", "package.json"],
            ),
            tmp_path,
        )
        assert targets == []

    def test_incremental_no_changed_files(self, runner: GoLinter, tmp_path) -> None:
        targets = runner._get_targets(
            DetectorContext(
                repo_root=str(tmp_path),
                scope=ScopeType.INCREMENTAL,
            ),
            tmp_path,
        )
        assert targets == []
