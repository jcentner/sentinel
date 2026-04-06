"""Tests for the eslint/biome runner detector."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from sentinel.detectors.eslint_runner import EslintRunner, _has_js_files
from sentinel.models import DetectorContext, DetectorTier, ScopeType, Severity


@pytest.fixture
def runner():
    return EslintRunner()


SAMPLE_ESLINT_OUTPUT = json.dumps([
    {
        "filePath": "/tmp/repo/src/app.ts",
        "messages": [
            {
                "ruleId": "no-unused-vars",
                "severity": 1,
                "message": "'x' is assigned a value but never used.",
                "line": 3,
                "column": 7,
                "endLine": 3,
                "endColumn": 8,
            },
            {
                "ruleId": "no-eval",
                "severity": 2,
                "message": "eval can be harmful.",
                "line": 10,
                "column": 1,
                "endLine": 10,
                "endColumn": 15,
            },
        ],
        "errorCount": 1,
        "warningCount": 1,
    },
    {
        "filePath": "/tmp/repo/clean.js",
        "messages": [],
        "errorCount": 0,
        "warningCount": 0,
    },
])

SAMPLE_BIOME_OUTPUT = json.dumps({
    "diagnostics": [
        {
            "category": "lint/correctness/noUnusedVariables",
            "severity": "warning",
            "message": [{"content": "This variable is unused."}],
            "location": {
                "path": {"file": "/tmp/repo/src/index.ts"},
                "span": {"start": 42, "end": 55},
            },
        },
        {
            "category": "lint/suspicious/noExplicitAny",
            "severity": "error",
            "message": [{"content": "Unexpected any. Specify a different type."}],
            "location": {
                "path": {"file": "/tmp/repo/src/utils.ts"},
                "span": {"start": 100, "end": 103},
            },
        },
    ],
})


class TestEslintRunnerProperties:
    def test_name(self, runner):
        assert runner.name == "eslint-runner"

    def test_description(self, runner):
        assert "ESLint" in runner.description or "Biome" in runner.description

    def test_tier(self, runner):
        assert runner.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, runner):
        assert "code-quality" in runner.categories


class TestHasJsFiles:
    def test_no_js_files(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        assert _has_js_files(tmp_path) is False

    def test_with_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text("{}\n")
        assert _has_js_files(tmp_path) is True

    def test_with_ts_files(self, tmp_path):
        (tmp_path / "app.ts").write_text("const x = 1;\n")
        assert _has_js_files(tmp_path) is True

    def test_with_jsx_files(self, tmp_path):
        (tmp_path / "component.jsx").write_text("export default () => <div/>;\n")
        assert _has_js_files(tmp_path) is True


class TestEslintParsing:
    def test_parse_eslint_output(self, runner):
        from pathlib import Path
        data = json.loads(SAMPLE_ESLINT_OUTPUT)
        findings = runner._parse_eslint_output(data, Path("/tmp/repo"))

        assert len(findings) == 2

        # First finding: warning severity
        f1 = findings[0]
        assert f1.detector == "eslint-runner"
        assert f1.severity == Severity.LOW  # severity=1 → LOW
        assert "no-unused-vars" in f1.title
        assert f1.file_path == "src/app.ts"
        assert f1.line_start == 3
        assert f1.confidence == 1.0

        # Second finding: high-severity security rule
        f2 = findings[1]
        assert f2.severity == Severity.HIGH  # no-eval → HIGH
        assert "no-eval" in f2.title
        assert f2.line_start == 10

    def test_parse_eslint_empty_file(self, runner):
        from pathlib import Path
        data = [{"filePath": "/tmp/repo/clean.js", "messages": []}]
        findings = runner._parse_eslint_output(data, Path("/tmp/repo"))
        assert findings == []

    def test_parse_eslint_relative_path(self, runner):
        from pathlib import Path
        data = [{
            "filePath": "/tmp/repo/deep/nested/file.ts",
            "messages": [{
                "ruleId": "no-console",
                "severity": 1,
                "message": "Unexpected console statement.",
                "line": 5,
            }],
        }]
        findings = runner._parse_eslint_output(data, Path("/tmp/repo"))
        assert findings[0].file_path == "deep/nested/file.ts"


class TestBiomeParsing:
    def test_parse_biome_output(self, runner):
        from pathlib import Path
        data = json.loads(SAMPLE_BIOME_OUTPUT)
        findings = runner._parse_biome_output(data, Path("/tmp/repo"))

        assert len(findings) == 2

        # First: correctness category, warning → LOW
        f1 = findings[0]
        assert f1.detector == "eslint-runner"
        assert f1.severity == Severity.LOW
        assert "noUnusedVariables" in f1.title
        assert f1.file_path == "src/index.ts"
        assert f1.confidence == 1.0

        # Second: suspicious category → elevated to HIGH
        f2 = findings[1]
        assert f2.severity == Severity.HIGH
        assert "noExplicitAny" in f2.title
        assert f2.file_path == "src/utils.ts"

    def test_parse_biome_empty(self, runner):
        from pathlib import Path
        findings = runner._parse_biome_output({"diagnostics": []}, Path("/tmp/repo"))
        assert findings == []


class TestEslintDetection:
    def test_skips_non_js_repos(self, runner, tmp_path):
        """Should return empty for repos with no JS/TS files."""
        (tmp_path / "main.py").write_text("x = 1\n")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.eslint_runner.subprocess.run")
    def test_biome_preferred_over_eslint(self, mock_run, runner, tmp_path):
        """Should try biome first."""
        (tmp_path / "app.ts").write_text("const x = 1;\n")
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_BIOME_OUTPUT,
            returncode=0,
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = runner.detect(ctx)

        # biome was called first
        call_args = mock_run.call_args_list[0]
        assert "biome" in call_args[0][0][0]
        assert len(findings) == 2

    @patch("sentinel.detectors.eslint_runner.subprocess.run")
    def test_falls_back_to_eslint(self, mock_run, runner, tmp_path):
        """Should fall back to eslint when biome is not found."""
        (tmp_path / "app.js").write_text("var x = 1;\n")

        def side_effect(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[0] == "biome":
                raise FileNotFoundError("biome not found")
            return MagicMock(stdout=SAMPLE_ESLINT_OUTPUT, returncode=1)

        mock_run.side_effect = side_effect

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = runner.detect(ctx)
        assert len(findings) == 2
        # eslint was called
        assert mock_run.call_count == 2

    @patch("sentinel.detectors.eslint_runner.subprocess.run")
    def test_neither_tool_available(self, mock_run, runner, tmp_path):
        """Should return empty when neither biome nor eslint is available."""
        (tmp_path / "app.js").write_text("var x = 1;\n")
        mock_run.side_effect = FileNotFoundError("not found")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.eslint_runner.subprocess.run")
    def test_incremental_scope_filters_js_files(self, mock_run, runner, tmp_path):
        """Incremental scope should only target changed JS/TS files."""
        (tmp_path / "changed.ts").write_text("const x = 1;\n")
        (tmp_path / "unchanged.ts").write_text("const y = 2;\n")

        mock_run.return_value = MagicMock(
            stdout=json.dumps({"diagnostics": []}),
            returncode=0,
        )

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["changed.ts", "also_changed.py"],
        )
        runner.detect(ctx)

        # Only changed.ts should be passed (not .py, not unchanged.ts)
        call_args = mock_run.call_args_list[0][0][0]
        assert "changed.ts" in call_args
        assert "also_changed.py" not in call_args

    @patch("sentinel.detectors.eslint_runner.subprocess.run")
    def test_timeout_handled_gracefully(self, mock_run, runner, tmp_path):
        """Timeout should not crash the detector."""
        import subprocess
        (tmp_path / "app.js").write_text("var x = 1;\n")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="biome", timeout=120)

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = runner.detect(ctx)
        assert findings == []
