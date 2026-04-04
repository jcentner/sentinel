"""End-to-end integration test for the full Sentinel pipeline."""

from __future__ import annotations

import subprocess

import pytest

from sentinel.core.runner import run_scan
from sentinel.store.db import get_connection
from sentinel.store.findings import (
    get_findings_by_run,
    suppress_finding,
)
from sentinel.store.runs import get_run_by_id


@pytest.fixture
def test_repo(tmp_path):
    """Create a realistic test repo with known issues."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo for blame support
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), capture_output=True,
    )

    # Create files with known issues
    src = repo / "src"
    src.mkdir()

    (src / "main.py").write_text(
        "import os\n"
        "import sys\n"
        "\n"
        "# TODO: refactor this module\n"
        "def main():\n"
        "    pass\n"
        "\n"
        "# FIXME: broken error handling\n"
        "def handler():\n"
        "    pass\n"
    )

    (src / "utils.py").write_text(
        "# HACK: temporary workaround for API rate limiting\n"
        "def retry():\n"
        "    pass\n"
    )

    (repo / "clean.py").write_text(
        "def clean_function():\n"
        "    return 42\n"
    )

    # Commit so git blame works
    subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo), capture_output=True,
    )

    return repo


@pytest.fixture
def db_conn(tmp_path):
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    conn = get_connection(db_dir / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def out_dir(tmp_path):
    """Output directory outside the test repo."""
    d = tmp_path / "output"
    d.mkdir()
    return d


class TestEndToEnd:
    def test_full_scan_produces_findings(self, test_repo, db_conn, out_dir):
        """A repo with known issues produces findings in the report."""
        run, findings, report = run_scan(
            str(test_repo), db_conn, skip_judge=True,
            output_path=str(out_dir / "report.md"),
        )

        # Should find TODOs/FIXMEs/HACKs and lint issues
        assert len(findings) >= 3  # At minimum: TODO, FIXME, HACK
        assert run.id is not None

        # Report contains expected elements
        assert "Sentinel Morning Report" in report
        assert "TODO" in report or "FIXME" in report

    def test_findings_stored_in_db(self, test_repo, db_conn, out_dir):
        """Findings are persisted in the database."""
        run, findings, _ = run_scan(
            str(test_repo), db_conn, skip_judge=True,
            output_path=str(out_dir / "report.md"),
        )

        stored = get_findings_by_run(db_conn, run.id)
        assert len(stored) == len(findings)
        assert all(f.fingerprint for f in stored)

    def test_run_completed_in_db(self, test_repo, db_conn, out_dir):
        """Run record is properly completed."""
        run, findings, _ = run_scan(
            str(test_repo), db_conn, skip_judge=True,
            output_path=str(out_dir / "report.md"),
        )

        db_run = get_run_by_id(db_conn, run.id)
        assert db_run.completed_at is not None
        assert db_run.finding_count == len(findings)

    def test_dedup_across_runs(self, test_repo, db_conn, out_dir):
        """Second run deduplicates against first run."""
        out1 = str(out_dir / "out1.md")
        out2 = str(out_dir / "out2.md")
        _run1, findings1, _ = run_scan(
            str(test_repo), db_conn, skip_judge=True, output_path=out1,
        )
        _run2, findings2, _report2 = run_scan(
            str(test_repo), db_conn, skip_judge=True, output_path=out2,
        )

        # Same findings count (recurring, not filtered out)
        assert len(findings2) == len(findings1)
        # Recurring flag should be set
        recurring = [f for f in findings2 if f.context and f.context.get("recurring")]
        assert len(recurring) == len(findings2)

    def test_suppress_excludes_from_report(self, test_repo, db_conn, out_dir):
        """Suppressed findings don't appear in subsequent runs."""
        out1 = str(out_dir / "out1.md")
        out2 = str(out_dir / "out2.md")
        _run1, findings1, _ = run_scan(
            str(test_repo), db_conn, skip_judge=True, output_path=out1,
        )
        assert len(findings1) > 0

        # Suppress the first finding
        suppress_finding(db_conn, findings1[0].fingerprint, reason="FP")

        # Second run should have one fewer finding
        _run2, findings2, _ = run_scan(
            str(test_repo), db_conn, skip_judge=True, output_path=out2,
        )
        assert len(findings2) == len(findings1) - 1

    def test_report_written_to_file(self, test_repo, db_conn, out_dir):
        """Report is written to the specified output path."""
        out = out_dir / "written_report.md"
        run_scan(
            str(test_repo), db_conn,
            skip_judge=True,
            output_path=str(out),
        )
        assert out.exists()
        contents = out.read_text()
        assert "Sentinel Morning Report" in contents

    def test_git_blame_enriches_findings(self, test_repo, db_conn, out_dir):
        """TODO scanner includes git blame info when available."""
        _, findings, _ = run_scan(
            str(test_repo), db_conn, skip_judge=True,
            output_path=str(out_dir / "report.md"),
        )

        todo_findings = [f for f in findings if f.detector == "todo-scanner"]
        assert len(todo_findings) >= 1
        # At least one should have git blame evidence
        has_blame = any(
            any(e.type.value == "git_history" for e in f.evidence)
            for f in todo_findings
        )
        assert has_blame

    def test_lint_findings_present(self, test_repo, db_conn, out_dir):
        """Lint runner detects unused imports."""
        _, findings, _ = run_scan(
            str(test_repo), db_conn, skip_judge=True,
            output_path=str(out_dir / "report.md"),
        )

        lint_findings = [f for f in findings if f.detector == "lint-runner"]
        assert len(lint_findings) >= 1  # At least unused import(s)
