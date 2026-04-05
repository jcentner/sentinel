"""Precision/recall evaluation against the seeded sample-repo fixture.

This test runs the full pipeline against a repo with known ground truth
and verifies that all expected findings are present and no false positives
are produced by the detectors we control (docs-drift, todo-scanner, lint-runner).

Ground truth is defined in tests/fixtures/sample-repo/ground-truth.toml
and shared with the `sentinel eval` CLI command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel.core.eval import evaluate, load_ground_truth
from sentinel.core.runner import run_scan
from sentinel.store.db import get_connection

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample-repo"
GROUND_TRUTH_PATH = FIXTURE_DIR / "ground-truth.toml"


@pytest.fixture(scope="module")
def ground_truth():
    """Load the shared ground truth definition."""
    if not GROUND_TRUTH_PATH.exists():
        pytest.skip("ground-truth.toml not found")
    return load_ground_truth(GROUND_TRUTH_PATH)


@pytest.fixture(scope="module")
def scan_results():
    """Run a full scan against the sample-repo fixture (no LLM judge)."""
    if not FIXTURE_DIR.exists():
        pytest.skip("sample-repo fixture not found")

    conn = get_connection(":memory:")
    _, findings, report = run_scan(
        str(FIXTURE_DIR),
        conn,
        skip_judge=True,
        output_path="/dev/null",
    )
    conn.close()
    return findings, report


@pytest.fixture(scope="module")
def eval_result(scan_results, ground_truth):
    """Evaluate findings against ground truth."""
    findings, _ = scan_results
    return evaluate(findings, ground_truth)


class TestPrecisionRecall:
    """Evaluate detector accuracy against known ground truth."""

    def test_all_expected_findings_present(self, eval_result):
        """Recall: every expected true positive should be in the results."""
        assert not eval_result.missing, (
            f"Missing {len(eval_result.missing)} expected findings:\n"
            + "\n".join(
                f"  - {m['detector']}: {m.get('file_path', '?')} / {m.get('title', '?')}"
                for m in eval_result.missing
            )
        )

    def test_no_known_false_positives(self, eval_result):
        """Precision: known FP patterns should not appear."""
        assert not eval_result.unexpected_fps, (
            f"Found {len(eval_result.unexpected_fps)} false positives:\n"
            + "\n".join(f"  - {fp}" for fp in eval_result.unexpected_fps)
        )

    def test_precision_at_k(self, eval_result):
        """Precision@k: of all findings, at least 70% should be true positives (ADR-008)."""
        assert eval_result.precision >= 0.70, (
            f"Precision = {eval_result.precision:.0%} "
            f"({eval_result.true_positives}/{eval_result.total_findings} TP), target ≥70%"
        )

    def test_recall(self, eval_result):
        """Recall: at least 90% of expected TPs should be found."""
        assert eval_result.recall >= 0.90, (
            f"Recall = {eval_result.recall:.0%}, target ≥90%"
        )

    def test_report_generated(self, scan_results):
        """The report string should be non-empty and contain findings."""
        _, report = scan_results
        assert "Sentinel Morning Report" in report
        assert "Findings" in report


class TestFalsePositivePrevention:
    """Targeted tests for specific FP-prevention mechanisms."""

    def test_code_block_links_not_flagged(self, scan_results, ground_truth):
        """Links inside fenced code blocks should not be checked."""
        findings, _ = scan_results
        exclude = set(ground_truth.get("exclude_detectors", []))
        filtered = [f for f in findings if f.detector not in exclude]
        code_block_fps = [
            f for f in filtered
            if f.detector == "docs-drift"
            and f.file_path == "README.md"
            and any(s in f.title for s in ["nonexistent", "does_not_exist", "path/to/"])
        ]
        assert code_block_fps == [], (
            f"Found {len(code_block_fps)} code-block FPs: "
            + ", ".join(f.title for f in code_block_fps)
        )

    def test_string_literal_todos_not_flagged(self, scan_results, ground_truth):
        """TODOs inside string literals should be filtered."""
        findings, _ = scan_results
        exclude = set(ground_truth.get("exclude_detectors", []))
        filtered = [f for f in findings if f.detector not in exclude]
        string_fps = [
            f for f in filtered
            if f.detector == "todo-scanner"
            and "fake" in f.title.lower()
        ]
        assert string_fps == [], "String literal TODO was falsely flagged"

    def test_valid_links_not_flagged(self, scan_results, ground_truth):
        """Valid links to existing files should not produce findings."""
        findings, _ = scan_results
        exclude = set(ground_truth.get("exclude_detectors", []))
        filtered = [f for f in findings if f.detector not in exclude]
        readme_fps = [
            f for f in filtered
            if f.detector == "docs-drift"
            and "getting-started" in (f.file_path or "")
            and "README" in f.title
        ]
        assert readme_fps == [], "Valid ../../README.md link was falsely flagged"
