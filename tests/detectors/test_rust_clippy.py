"""Tests for the Rust clippy detector."""

from __future__ import annotations

import json
import subprocess as sp
from unittest.mock import MagicMock, patch

import pytest

from sentinel.detectors.rust_clippy import RustClippy, _has_rust_files, _is_high_severity_lint
from sentinel.models import DetectorContext, DetectorTier, ScopeType, Severity


@pytest.fixture
def runner() -> RustClippy:
    return RustClippy()


def _make_clippy_line(
    message: str,
    level: str = "warning",
    lint: str = "clippy::needless_return",
    filename: str = "src/main.rs",
    line_start: int = 10,
    line_end: int = 10,
    snippet: str = "return x;",
) -> str:
    """Build a single JSON-lines entry matching cargo clippy output."""
    obj = {
        "reason": "compiler-message",
        "message": {
            "level": level,
            "message": message,
            "code": {"code": lint, "explanation": None} if lint else None,
            "spans": [
                {
                    "file_name": filename,
                    "line_start": line_start,
                    "line_end": line_end,
                    "column_start": 1,
                    "column_end": 10,
                    "is_primary": True,
                    "text": [{"text": snippet, "highlight_start": 1, "highlight_end": 10}] if snippet else [],
                }
            ],
        },
    }
    return json.dumps(obj)


SAMPLE_CLIPPY_OUTPUT = "\n".join([
    _make_clippy_line(
        "unneeded `return` statement",
        level="warning",
        lint="clippy::needless_return",
        filename="src/main.rs",
        line_start=15,
        line_end=15,
        snippet="return result;",
    ),
    _make_clippy_line(
        "this looks like you are swapping `a` and `b` manually",
        level="warning",
        lint="clippy::suspicious::manual_swap",
        filename="src/lib.rs",
        line_start=42,
        line_end=44,
        snippet="let tmp = a;",
    ),
    _make_clippy_line(
        "unused variable: `x`",
        level="warning",
        lint="clippy::unused_variables",
        filename="src/utils.rs",
        line_start=8,
        line_end=8,
        snippet="let x = 5;",
    ),
    # Non-compiler-message lines (should be ignored)
    json.dumps({"reason": "build-script-executed", "package_id": "test 0.1.0"}),
    json.dumps({"reason": "compiler-artifact", "target": {"name": "test"}}),
])


# ── Detector properties ──────────────────────────────────────────────


class TestRustClippyProperties:
    def test_name(self, runner: RustClippy) -> None:
        assert runner.name == "rust-clippy"

    def test_description(self, runner: RustClippy) -> None:
        assert "clippy" in runner.description.lower() or "Rust" in runner.description

    def test_tier(self, runner: RustClippy) -> None:
        assert runner.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, runner: RustClippy) -> None:
        assert "code-quality" in runner.categories


# ── Rust file detection ──────────────────────────────────────────────


class TestHasRustFiles:
    def test_detects_cargo_toml(self, tmp_path: MagicMock) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "myproject"')
        assert _has_rust_files(tmp_path) is True

    def test_detects_rs_source_file(self, tmp_path: MagicMock) -> None:
        (tmp_path / "main.rs").write_text("fn main() {}")
        assert _has_rust_files(tmp_path) is True

    def test_skips_target_dir(self, tmp_path: MagicMock) -> None:
        target = tmp_path / "target" / "debug"
        target.mkdir(parents=True)
        (target / "deps.rs").write_text("// build artifact")
        assert _has_rust_files(tmp_path) is False

    def test_no_rust_files(self, tmp_path: MagicMock) -> None:
        (tmp_path / "main.py").write_text("print('hello')")
        assert _has_rust_files(tmp_path) is False

    def test_empty_dir(self, tmp_path: MagicMock) -> None:
        assert _has_rust_files(tmp_path) is False


# ── High severity lint check ─────────────────────────────────────────


class TestHighSeverityLint:
    def test_correctness_group(self) -> None:
        assert _is_high_severity_lint("clippy::correctness") is True

    def test_correctness_prefix(self) -> None:
        assert _is_high_severity_lint("clippy::correctness::approx_constant") is True

    def test_suspicious_group(self) -> None:
        assert _is_high_severity_lint("clippy::suspicious") is True

    def test_suspicious_prefix(self) -> None:
        assert _is_high_severity_lint("clippy::suspicious::manual_swap") is True

    def test_style_lint_not_high(self) -> None:
        assert _is_high_severity_lint("clippy::style::needless_return") is False

    def test_regular_lint_not_high(self) -> None:
        assert _is_high_severity_lint("clippy::needless_return") is False

    def test_empty_string(self) -> None:
        assert _is_high_severity_lint("") is False


# ── Output parsing ───────────────────────────────────────────────────


class TestParseOutput:
    def test_parse_findings_count(self, runner: RustClippy) -> None:
        """Only compiler-message entries are parsed."""
        findings = runner._parse_output(SAMPLE_CLIPPY_OUTPUT, MagicMock())
        assert len(findings) == 3

    def test_severity_mapping_warning(self, runner: RustClippy) -> None:
        """Regular warning → MEDIUM."""
        findings = runner._parse_output(SAMPLE_CLIPPY_OUTPUT, MagicMock())
        needless = next(f for f in findings if "needless_return" in f.title)
        assert needless.severity == Severity.MEDIUM

    def test_severity_mapping_suspicious(self, runner: RustClippy) -> None:
        """suspicious:: prefix → HIGH."""
        findings = runner._parse_output(SAMPLE_CLIPPY_OUTPUT, MagicMock())
        swap = next(f for f in findings if "manual_swap" in f.title)
        assert swap.severity == Severity.HIGH

    def test_finding_metadata(self, runner: RustClippy) -> None:
        findings = runner._parse_output(SAMPLE_CLIPPY_OUTPUT, MagicMock())
        needless = next(f for f in findings if "needless_return" in f.title)
        assert needless.file_path == "src/main.rs"
        assert needless.line_start == 15
        assert needless.detector == "rust-clippy"
        assert needless.category == "code-quality"
        assert needless.confidence == 1.0
        assert len(needless.evidence) == 1
        assert needless.context == {"lint": "clippy::needless_return", "tool": "cargo-clippy"}

    def test_evidence_includes_snippet(self, runner: RustClippy) -> None:
        findings = runner._parse_output(SAMPLE_CLIPPY_OUTPUT, MagicMock())
        needless = next(f for f in findings if "needless_return" in f.title)
        assert "return result;" in needless.evidence[0].content

    def test_empty_output(self, runner: RustClippy) -> None:
        assert runner._parse_output("", MagicMock()) == []

    def test_invalid_json_lines_skipped(self, runner: RustClippy) -> None:
        output = "not json\n" + _make_clippy_line("test warning")
        findings = runner._parse_output(output, MagicMock())
        assert len(findings) == 1

    def test_no_primary_span_skipped(self, runner: RustClippy) -> None:
        """Messages without a primary span are skipped."""
        obj = {
            "reason": "compiler-message",
            "message": {
                "level": "warning",
                "message": "orphan message",
                "code": None,
                "spans": [],
            },
        }
        assert runner._parse_output(json.dumps(obj), MagicMock()) == []

    def test_absolute_path_skipped(self, runner: RustClippy) -> None:
        """Findings with absolute paths (compiler internals) are skipped."""
        line = _make_clippy_line(
            "internal issue",
            filename="/rustc/abc123/library/core/src/ops.rs",
        )
        assert runner._parse_output(line, MagicMock()) == []

    def test_error_severity(self, runner: RustClippy) -> None:
        line = _make_clippy_line("type mismatch", level="error", lint="")
        findings = runner._parse_output(line, MagicMock())
        assert findings[0].severity == Severity.HIGH

    def test_no_lint_code(self, runner: RustClippy) -> None:
        """Findings without a lint code use level as title prefix."""
        line = _make_clippy_line("some error", level="error", lint="")
        findings = runner._parse_output(line, MagicMock())
        assert findings[0].title.startswith("[error]")

    def test_deduplication(self, runner: RustClippy) -> None:
        """Same file:line:message is deduplicated."""
        line = _make_clippy_line("dup warning", filename="src/a.rs", line_start=5)
        output = line + "\n" + line
        findings = runner._parse_output(output, MagicMock())
        assert len(findings) == 1

    def test_no_snippet(self, runner: RustClippy) -> None:
        """Findings without snippet text still work."""
        line = _make_clippy_line("no snippet warning", snippet="")
        findings = runner._parse_output(line, MagicMock())
        assert len(findings) == 1
        assert "no snippet warning" in findings[0].evidence[0].content


# ── Detection (with mocked subprocess) ──────────────────────────────


class TestDetection:
    def test_skips_non_rust_repo(self, runner: RustClippy, tmp_path: MagicMock) -> None:
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.rust_clippy.subprocess.run")
    def test_detects_with_clippy(self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        mock_run.return_value = MagicMock(stdout=SAMPLE_CLIPPY_OUTPUT)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert len(findings) == 3
        mock_run.assert_called_once()

    @patch("sentinel.detectors.rust_clippy.subprocess.run", side_effect=FileNotFoundError)
    def test_no_cargo_installed(self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.rust_clippy.subprocess.run")
    def test_timeout_handling(self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock) -> None:
        mock_run.side_effect = sp.TimeoutExpired(cmd="cargo", timeout=300)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert findings == []


# ── Scope filtering ──────────────────────────────────────────────────


class TestScopeFiltering:
    @patch("sentinel.detectors.rust_clippy.subprocess.run")
    def test_incremental_filters_to_changed_rs_files(
        self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock
    ) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        mock_run.return_value = MagicMock(stdout=SAMPLE_CLIPPY_OUTPUT)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["src/main.rs"],  # only this file changed
        )
        findings = runner.detect(ctx)
        # Should only include findings from src/main.rs
        assert all(f.file_path == "src/main.rs" for f in findings)
        assert len(findings) == 1

    @patch("sentinel.detectors.rust_clippy.subprocess.run")
    def test_incremental_no_rs_changed(
        self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock
    ) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        mock_run.return_value = MagicMock(stdout=SAMPLE_CLIPPY_OUTPUT)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["README.md"],
        )
        findings = runner.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.rust_clippy.subprocess.run")
    def test_targeted_filters_to_target_paths(
        self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock
    ) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        mock_run.return_value = MagicMock(stdout=SAMPLE_CLIPPY_OUTPUT)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.TARGETED,
            target_paths=["src/lib.rs"],
        )
        findings = runner.detect(ctx)
        assert all(f.file_path == "src/lib.rs" for f in findings)

    @patch("sentinel.detectors.rust_clippy.subprocess.run")
    def test_targeted_directory(
        self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock
    ) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        mock_run.return_value = MagicMock(stdout=SAMPLE_CLIPPY_OUTPUT)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.TARGETED,
            target_paths=["src"],
        )
        findings = runner.detect(ctx)
        # All 3 sample findings are under src/
        assert len(findings) == 3

    @patch("sentinel.detectors.rust_clippy.subprocess.run")
    def test_full_scan_returns_all(
        self, mock_run: MagicMock, runner: RustClippy, tmp_path: MagicMock
    ) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        mock_run.return_value = MagicMock(stdout=SAMPLE_CLIPPY_OUTPUT)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
        )
        findings = runner.detect(ctx)
        assert len(findings) == 3
