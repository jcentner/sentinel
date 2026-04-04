"""Repeatability test — same repo state produces identical findings."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from sentinel.core.runner import run_scan
from sentinel.store.db import get_connection


@pytest.fixture
def stable_repo(tmp_path):
    """A deterministic test repo with known content."""
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), capture_output=True,
    )

    (repo / "main.py").write_text(
        "import os\n"
        "\n"
        "# TODO: fix the widget\n"
        "def widget():\n"
        "    pass\n"
    )

    (repo / "utils.py").write_text(
        "# FIXME: broken retry logic\n"
        "def retry():\n"
        "    pass\n"
    )

    subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo), capture_output=True,
    )

    return repo


class TestRepeatability:
    def test_deterministic_findings_across_runs(self, stable_repo, tmp_path):
        """Two runs on identical repo state produce identical findings."""
        db1 = get_connection(tmp_path / "db1.db")
        db2 = get_connection(tmp_path / "db2.db")

        out1 = tmp_path / "report1.md"
        out2 = tmp_path / "report2.md"

        try:
            _, findings1, _ = run_scan(
                str(stable_repo), db1,
                skip_judge=True,
                output_path=str(out1),
            )
            _, findings2, _ = run_scan(
                str(stable_repo), db2,
                skip_judge=True,
                output_path=str(out2),
            )

            # Same number of findings
            assert len(findings1) == len(findings2)

            # Same fingerprints (order-independent)
            fps1 = sorted(f.fingerprint for f in findings1)
            fps2 = sorted(f.fingerprint for f in findings2)
            assert fps1 == fps2

            # Same detectors, categories, titles
            details1 = sorted(
                (f.detector, f.category, f.title, f.severity.value, f.file_path)
                for f in findings1
            )
            details2 = sorted(
                (f.detector, f.category, f.title, f.severity.value, f.file_path)
                for f in findings2
            )
            assert details1 == details2

        finally:
            db1.close()
            db2.close()

    def test_deterministic_report_content(self, stable_repo, tmp_path):
        """Deterministic detectors produce reports with identical finding sections."""
        db1 = get_connection(tmp_path / "db1.db")
        db2 = get_connection(tmp_path / "db2.db")

        out1 = tmp_path / "report1.md"
        out2 = tmp_path / "report2.md"

        try:
            run_scan(
                str(stable_repo), db1,
                skip_judge=True,
                output_path=str(out1),
            )
            run_scan(
                str(stable_repo), db2,
                skip_judge=True,
                output_path=str(out2),
            )

            r1 = out1.read_text()
            r2 = out2.read_text()

            # Strip the timestamp line (which does vary) and compare
            lines1 = [l for l in r1.splitlines() if not l.startswith("**Scan**:")]
            lines2 = [l for l in r2.splitlines() if not l.startswith("**Scan**:")]
            assert lines1 == lines2

        finally:
            db1.close()
            db2.close()

    def test_fingerprint_stability(self, stable_repo, tmp_path):
        """Fingerprints are deterministic — same content → same hash."""
        db = get_connection(tmp_path / "db.db")

        try:
            _, findings, _ = run_scan(
                str(stable_repo), db,
                skip_judge=True,
                output_path=str(tmp_path / "report.md"),
            )

            # All findings should have non-empty fingerprints
            for f in findings:
                assert f.fingerprint, f"Missing fingerprint for {f.title}"
                assert len(f.fingerprint) == 16, f"Unexpected fingerprint length for {f.title}"

        finally:
            db.close()
