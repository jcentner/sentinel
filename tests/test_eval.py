"""Precision/recall evaluation against the seeded sample-repo fixture.

This test runs the full pipeline against a repo with known ground truth
and verifies that all expected findings are present and no false positives
are produced by the detectors we control (docs-drift, todo-scanner, lint-runner).

dep-audit is excluded because it audits the current Python environment,
not the target repo's declared dependencies — see TD-006.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel.core.runner import run_scan
from sentinel.store.db import get_connection

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample-repo"


# ── Ground truth definition ───────────────────────────────────────

# Each tuple: (detector, file_path_contains, title_contains)
EXPECTED_TRUE_POSITIVES = [
    # docs-drift: stale references
    ("docs-drift", "README.md", "old_handler.py"),
    ("docs-drift", "README.md", "docs/api.md"),
    ("docs-drift", "getting-started.md", "overview.md"),
    # docs-drift: dependency drift
    ("docs-drift", "README.md", "flask"),
    ("docs-drift", "README.md", "numpy"),  # indented code block
    # todo-fixme
    ("todo-scanner", "config.py", "TODO"),
    ("todo-scanner", "main.py", "Add proper logging"),
    ("todo-scanner", "main.py", "FIXME"),
    ("todo-scanner", "main.py", "HACK"),
    ("todo-scanner", "main.py", "this IS a real comment"),
    ("todo-scanner", "main.py", "XXX"),
    # lint
    ("lint-runner", "main.py", "F401"),
    ("lint-runner", "main.py", "F841"),
]

# Things that should NOT appear — would be false positives
EXPECTED_FALSE_POSITIVES = [
    # Code block content should not be flagged
    ("docs-drift", "README.md", "does_not_exist.py"),
    ("docs-drift", "README.md", "nonexistent_file.py"),
    ("docs-drift", "README.md", "path/to/nonexistent.md"),
    # String literal TODOs should not be flagged
    ("todo-scanner", "main.py", "inside a string"),
    ("todo-scanner", "main.py", "fake"),
    # Mid-sentence TODO mention should not be flagged
    ("todo-scanner", "main.py", "find TODOs"),
]


def _match_finding(finding, detector: str, path_substr: str, title_substr: str) -> bool:
    """Check if a finding matches the expected pattern."""
    if finding.detector != detector:
        return False
    file_path = finding.file_path or ""
    if path_substr not in file_path:
        return False
    return title_substr.lower() in finding.title.lower()


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

    # Exclude dep-audit findings (audits wrong env — known limitation)
    findings = [f for f in findings if f.detector != "dep-audit"]
    return findings, report


class TestPrecisionRecall:
    """Evaluate detector accuracy against known ground truth."""

    def test_all_expected_findings_present(self, scan_results):
        """Recall: every expected true positive should be in the results."""
        findings, _ = scan_results
        missing = []
        for detector, path_substr, title_substr in EXPECTED_TRUE_POSITIVES:
            matched = any(
                _match_finding(f, detector, path_substr, title_substr)
                for f in findings
            )
            if not matched:
                missing.append((detector, path_substr, title_substr))

        assert not missing, (
            f"Missing {len(missing)} expected findings:\n"
            + "\n".join(f"  - {d}: {p} / {t}" for d, p, t in missing)
        )

    def test_no_known_false_positives(self, scan_results):
        """Precision: known FP patterns should not appear."""
        findings, _ = scan_results
        found_fps = []
        for detector, path_substr, title_substr in EXPECTED_FALSE_POSITIVES:
            matched = [
                f for f in findings
                if _match_finding(f, detector, path_substr, title_substr)
            ]
            found_fps.extend(matched)

        assert not found_fps, (
            f"Found {len(found_fps)} false positives:\n"
            + "\n".join(f"  - [{f.detector}] {f.title} at {f.file_path}" for f in found_fps)
        )

    def test_precision_at_k(self, scan_results):
        """Precision@k: of all findings, at least 70% should be true positives (ADR-008)."""
        findings, _ = scan_results
        tp_count = 0
        for f in findings:
            is_tp = any(
                _match_finding(f, d, p, t)
                for d, p, t in EXPECTED_TRUE_POSITIVES
            )
            if is_tp:
                tp_count += 1

        precision = tp_count / len(findings) if findings else 0
        assert precision >= 0.70, (
            f"Precision@{len(findings)} = {precision:.0%} "
            f"({tp_count}/{len(findings)} true positives), target ≥70%"
        )

    def test_report_generated(self, scan_results):
        """The report string should be non-empty and contain findings."""
        _, report = scan_results
        assert "Sentinel Morning Report" in report
        assert "Findings" in report


class TestFalsePositivePrevention:
    """Targeted tests for specific FP-prevention mechanisms."""

    def test_code_block_links_not_flagged(self, scan_results):
        """Links inside fenced code blocks should not be checked."""
        findings, _ = scan_results
        code_block_fps = [
            f for f in findings
            if f.detector == "docs-drift"
            and f.file_path == "README.md"
            and any(s in f.title for s in ["nonexistent", "does_not_exist", "path/to/"])
        ]
        assert code_block_fps == [], (
            f"Found {len(code_block_fps)} code-block FPs: "
            + ", ".join(f.title for f in code_block_fps)
        )

    def test_string_literal_todos_not_flagged(self, scan_results):
        """TODOs inside string literals should be filtered."""
        findings, _ = scan_results
        string_fps = [
            f for f in findings
            if f.detector == "todo-scanner"
            and "fake" in f.title.lower()
        ]
        assert string_fps == [], "String literal TODO was falsely flagged"

    def test_valid_links_not_flagged(self, scan_results):
        """Valid links to existing files should not produce findings."""
        findings, _ = scan_results
        # getting-started.md links to ../../README.md which exists
        readme_fps = [
            f for f in findings
            if f.detector == "docs-drift"
            and "getting-started" in (f.file_path or "")
            and "README" in f.title
        ]
        assert readme_fps == [], "Valid ../../README.md link was falsely flagged"
