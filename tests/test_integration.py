"""End-to-end integration test for the full Sentinel pipeline."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from sentinel.core.runner import run_scan
from sentinel.store.db import get_connection
from sentinel.store.findings import (
    get_findings_by_run,
    suppress_finding,
)
from sentinel.store.llm_log import get_llm_log_for_run
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


class TestDocsDriftIntegration:
    """Integration tests for docs-drift detector in the full pipeline."""

    def test_docs_drift_finds_stale_links(self, tmp_path):
        """Docs-drift detector surfaces stale links in full pipeline."""
        repo = tmp_path / "repo"
        repo.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo), capture_output=True,
        )

        # README with a broken link
        (repo / "README.md").write_text(
            "# My Project\n\nSee [guide](docs/guide.md) for setup.\n"
        )
        subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo), capture_output=True,
        )

        db_dir = tmp_path / "db"
        db_dir.mkdir()
        conn = get_connection(db_dir / "test.db")
        out = tmp_path / "report.md"

        try:
            _run, findings, report = run_scan(
                str(repo), conn, skip_judge=True, output_path=str(out),
            )

            drift_findings = [f for f in findings if f.detector == "docs-drift"]
            assert len(drift_findings) >= 1
            assert any("guide" in f.title for f in drift_findings)
            assert "docs-drift" in report
        finally:
            conn.close()

    def test_docs_drift_dep_drift_in_pipeline(self, tmp_path):
        """Dependency drift findings appear in the pipeline."""
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

        # pyproject.toml with click
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "demo"\ndependencies = [\n'
            '    "click>=8.0",\n'
            "]\n"
        )
        # README mentions flask (not in deps)
        (repo / "README.md").write_text(
            "# Demo\n\n```bash\npip install click flask\n```\n"
        )
        subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo), capture_output=True,
        )

        db_dir = tmp_path / "db"
        db_dir.mkdir()
        conn = get_connection(db_dir / "test.db")
        out = tmp_path / "report.md"

        try:
            _run, findings, _report = run_scan(
                str(repo), conn, skip_judge=True, output_path=str(out),
            )

            dep_drift = [
                f for f in findings
                if f.context and f.context.get("pattern") == "dependency-drift"
            ]
            assert len(dep_drift) == 1
            assert "flask" in dep_drift[0].title.lower()
        finally:
            conn.close()


def _ollama_response(is_real: bool, severity: str = "medium"):
    """Create a mock httpx response matching Ollama /api/generate format."""
    return MagicMock(
        status_code=200,
        json=lambda: {
            "response": json.dumps({
                "is_real": is_real,
                "adjusted_severity": severity,
                "summary": "Confirmed" if is_real else "False positive",
                "reasoning": "Test reasoning",
            }),
            "eval_count": 30,
            "eval_duration": 500_000_000,
        },
        raise_for_status=lambda: None,
    )


class TestJudgeIntegration:
    """Integration tests that exercise the full pipeline including LLM judge.

    Only the Ollama HTTP endpoint is mocked — everything else (detectors,
    fingerprinting, dedup, context, persistence, report) runs for real.
    """

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_full_scan_with_judge(
        self, mock_check, mock_post, test_repo, db_conn, out_dir,
    ):
        """run_scan with judge enabled: findings get verdicts and are stored."""
        mock_check.return_value = True
        mock_post.return_value = _ollama_response(is_real=True, severity="medium")

        _run, findings, report = run_scan(
            str(test_repo), db_conn, skip_judge=False,
            output_path=str(out_dir / "report.md"),
        )

        assert len(findings) >= 3
        # Judge should have been called for each finding
        assert mock_post.call_count == len(findings)
        # All findings should have judge verdict metadata
        for f in findings:
            assert f.context is not None
            assert f.context.get("judge_verdict") == "confirmed"
            assert f.context["judge"]["summary"] == "Confirmed"
        # Report should contain judge output
        assert "confirmed" in report.lower() or "Confirmed" in report

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_judge_fp_reduces_confidence(
        self, mock_check, mock_post, test_repo, db_conn, out_dir,
    ):
        """When judge marks findings as FP, confidence drops and report shows it."""
        mock_check.return_value = True
        mock_post.return_value = _ollama_response(is_real=False, severity="low")

        _run, findings, _report = run_scan(
            str(test_repo), db_conn, skip_judge=False,
            output_path=str(out_dir / "report.md"),
        )

        assert len(findings) >= 1
        for f in findings:
            assert f.context.get("judge_verdict") == "likely_false_positive"
            assert f.confidence <= 0.3

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_judge_writes_llm_log(
        self, mock_check, mock_post, test_repo, db_conn, out_dir,
    ):
        """Full pipeline writes LLM log entries for each judged finding."""
        mock_check.return_value = True
        mock_post.return_value = _ollama_response(is_real=True)

        run, findings, _ = run_scan(
            str(test_repo), db_conn, skip_judge=False,
            output_path=str(out_dir / "report.md"),
        )

        log_rows = get_llm_log_for_run(db_conn, run.id)
        assert len(log_rows) == len(findings)
        for row in log_rows:
            assert row["purpose"] == "judge"
            assert row["prompt"] != ""
            assert row["verdict"] == "confirmed"
