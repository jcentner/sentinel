"""CLI integration tests using Click's CliRunner."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from sentinel.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def test_repo(tmp_path):
    """Create a small git repo with known issues."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), capture_output=True, check=True,
    )
    (repo / "main.py").write_text(
        "import os\n"
        "# TODO: fix this\n"
        "def f():\n"
        "    pass\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo), capture_output=True, check=True,
    )
    return repo


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


# ── scan command ─────────────────────────────────────────────────────


class TestScanCommand:
    def test_basic_scan(self, runner, test_repo, db_path, tmp_path):
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
        ])
        assert result.exit_code == 0
        assert "Scan complete:" in result.output
        assert "findings in run" in result.output
        assert Path(out).exists()

    def test_scan_nonexistent_repo(self, runner, tmp_path, db_path):
        result = runner.invoke(main, [
            "scan", str(tmp_path / "nope"),
            "--skip-judge", "--db", db_path,
        ])
        assert result.exit_code != 0

    def test_incremental_and_target_conflict(self, runner, test_repo, db_path):
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path,
            "--incremental", "--target", "main.py",
        ])
        assert result.exit_code != 0
        assert "Cannot use --incremental and --target together" in result.output

    def test_targeted_scan(self, runner, test_repo, db_path, tmp_path):
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
            "--target", "main.py",
        ])
        assert result.exit_code == 0
        assert "Scan complete:" in result.output

    def test_custom_detectors_dir_via_config(self, runner, test_repo, db_path, tmp_path):
        """Custom detectors loaded from detectors_dir config."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        (custom_dir / "hello.py").write_text(
            "from sentinel.detectors.base import Detector\n"
            "from sentinel.models import DetectorContext, DetectorTier, Finding, Severity\n"
            "\n"
            "class HelloDetector(Detector):\n"
            "    @property\n"
            "    def name(self): return 'hello-detector'\n"
            "    @property\n"
            "    def description(self): return 'Says hello'\n"
            "    @property\n"
            "    def tier(self): return DetectorTier.DETERMINISTIC\n"
            "    @property\n"
            "    def categories(self): return ['custom']\n"
            "    def detect(self, context):\n"
            "        return [Finding(\n"
            "            detector='hello-detector', category='custom',\n"
            "            title='Hello from custom', severity=Severity.LOW,\n"
            "            confidence=1.0, description='Custom finding',\n"
            "            evidence=[],\n"
            "        )]\n"
        )
        (test_repo / "sentinel.toml").write_text(
            f'[sentinel]\ndetectors_dir = "{custom_dir}"\n'
        )
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
        ])
        assert result.exit_code == 0
        # Custom detector should produce at least its one finding
        report = Path(out).read_text()
        assert "Hello from custom" in report

    def test_verbose_flag(self, runner, test_repo, db_path, tmp_path):
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "-v", "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
        ])
        assert result.exit_code == 0

    def test_incremental_no_changes(self, runner, test_repo, db_path, tmp_path):
        """Second incremental scan with no changes should exit early."""
        out1 = str(tmp_path / "r1.md")
        out2 = str(tmp_path / "r2.md")
        # First full scan to set baseline
        first = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out1,
        ])
        assert first.exit_code == 0, f"First scan failed: {first.output}"
        # Second incremental scan — no changes
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out2,
            "--incremental",
        ])
        assert result.exit_code == 0
        assert "No changes since last run" in result.output

    def test_scan_json_output(self, runner, test_repo, db_path, tmp_path):
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "run" in data
        assert "findings" in data
        assert "report_path" in data
        assert isinstance(data["run"]["id"], int)
        assert isinstance(data["findings"], list)
        if data["findings"]:
            f = data["findings"][0]
            assert "detector" in f
            assert "severity" in f
            assert "title" in f
            assert "fingerprint" in f


# ── suppress command ─────────────────────────────────────────────────


class TestSuppressCommand:
    def test_suppress_nonexistent_finding(self, runner, test_repo, db_path):
        # Initialize DB with a scan first
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "suppress", "99999",
            "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_suppress_existing_finding(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "suppress", "1",
            "--repo", str(test_repo), "--db", db_path,
            "-r", "False positive",
        ])
        assert result.exit_code == 0
        assert "Suppressed finding #1" in result.output

    def test_suppress_json_output(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "suppress", "1",
            "--repo", str(test_repo), "--db", db_path,
            "-r", "False positive", "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == 1
        assert data["status"] == "suppressed"
        assert data["reason"] == "False positive"
        assert "fingerprint" in data
        assert "title" in data

    def test_suppress_json_not_found(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "suppress", "99999",
            "--repo", str(test_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "error" in data


# ── approve command ──────────────────────────────────────────────────


class TestApproveCommand:
    def test_approve_nonexistent_finding(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "approve", "99999",
            "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_approve_existing_finding(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "approve", "1",
            "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Approved finding #1" in result.output
        assert "create-issues" in result.output

    def test_approve_json_output(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "approve", "1",
            "--repo", str(test_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == 1
        assert data["status"] == "approved"
        assert "fingerprint" in data
        assert "title" in data

    def test_approve_json_not_found(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "approve", "99999",
            "--repo", str(test_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "error" in data


# ── show command ─────────────────────────────────────────────────────


class TestShowCommand:
    def test_show_nonexistent_finding(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "show", "99999",
            "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_show_existing_finding(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "show", "1",
            "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Finding #1" in result.output
        assert "Title:" in result.output
        assert "Detector:" in result.output
        assert "Severity:" in result.output
        assert "Description:" in result.output

    def test_show_json_output(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "show", "1",
            "--repo", str(test_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "detector" in data
        assert "severity" in data
        assert "title" in data
        assert "evidence" in data
        assert "fingerprint" in data
        assert "status" in data


# ── history command ──────────────────────────────────────────────────


class TestHistoryCommand:
    def test_history_empty(self, runner, test_repo, db_path):
        result = runner.invoke(main, [
            "history", "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "No runs found" in result.output

    def test_history_after_scan(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "history", "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Findings" in result.output
        assert str(test_repo) in result.output

    def test_history_json_output_empty(self, runner, test_repo, db_path):
        result = runner.invoke(main, [
            "history", "--repo", str(test_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_history_json_output_after_scan(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "history", "--repo", str(test_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1
        run = data[0]
        assert "id" in run
        assert "scope" in run
        assert "finding_count" in run
        assert "repo_path" in run


# ── create-issues command ────────────────────────────────────────────


class TestCreateIssuesCommand:
    def test_no_approved_findings(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "create-issues",
            "--repo", str(test_repo), "--db", db_path, "--dry-run",
        ])
        assert result.exit_code == 0
        assert "No approved findings" in result.output

    def test_no_approved_findings_json(self, runner, test_repo, db_path):
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        result = runner.invoke(main, [
            "create-issues",
            "--repo", str(test_repo), "--db", db_path, "--dry-run",
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["results"] == []
        assert "No approved" in data["message"]

    def test_dry_run_without_github_config(self, runner, test_repo, db_path):
        """Dry run without GitHub config should show what would be created."""
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        # Approve a finding
        runner.invoke(main, [
            "approve", "1",
            "--repo", str(test_repo), "--db", db_path,
        ])
        result = runner.invoke(main, [
            "create-issues",
            "--repo", str(test_repo), "--db", db_path, "--dry-run",
        ], env={})
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_missing_github_config_no_dry_run(self, runner, test_repo, db_path):
        """Without GitHub config and no --dry-run, should fail."""
        runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", os.devnull,
        ])
        runner.invoke(main, [
            "approve", "1",
            "--repo", str(test_repo), "--db", db_path,
        ])
        result = runner.invoke(main, [
            "create-issues",
            "--repo", str(test_repo), "--db", db_path,
        ], env={})
        assert result.exit_code != 0
        assert "GitHub config required" in result.output


# ── eval command ─────────────────────────────────────────────────────


class TestEvalCommand:
    def test_eval_missing_ground_truth(self, runner, test_repo, db_path):
        result = runner.invoke(main, [
            "eval", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code != 0
        assert "Ground truth file not found" in result.output

    def test_eval_with_sample_repo(self, runner, db_path):
        """Eval against the built-in sample repo fixture."""
        sample_repo = Path(__file__).parent / "fixtures" / "sample-repo"
        if not sample_repo.exists():
            pytest.skip("sample-repo fixture not found")
        gt = sample_repo / "ground-truth.toml"
        if not gt.exists():
            pytest.skip("ground-truth.toml not found")
        result = runner.invoke(main, [
            "eval", str(sample_repo),
            "--ground-truth", str(gt), "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Precision:" in result.output
        assert "Recall:" in result.output
        assert "PASS" in result.output

    def test_eval_json_output(self, runner, db_path):
        """Eval JSON output against the built-in sample repo fixture."""
        sample_repo = Path(__file__).parent / "fixtures" / "sample-repo"
        if not sample_repo.exists():
            pytest.skip("sample-repo fixture not found")
        gt = sample_repo / "ground-truth.toml"
        if not gt.exists():
            pytest.skip("ground-truth.toml not found")
        result = runner.invoke(main, [
            "eval", str(sample_repo),
            "--ground-truth", str(gt), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "precision" in data
        assert "recall" in data
        assert "total_findings" in data
        assert "true_positives" in data
        assert "passed" in data
        assert data["passed"] is True
        assert data["precision"] >= 0.7
        assert data["recall"] >= 0.9


# ── eval-history command ─────────────────────────────────────────────


class TestEvalHistoryCommand:
    def test_eval_history_empty(self, runner, test_repo, db_path):
        """Eval history with no prior results shows message."""
        result = runner.invoke(main, [
            "eval-history", "--repo", str(test_repo), "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "No evaluation results found" in result.output

    def test_eval_history_json_empty(self, runner, test_repo, db_path):
        """Eval history JSON output returns empty list when no results."""
        result = runner.invoke(main, [
            "eval-history", "--repo", str(test_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_eval_history_after_eval(self, runner, db_path):
        """Eval history shows results after running eval."""
        sample_repo = Path(__file__).parent / "fixtures" / "sample-repo"
        if not sample_repo.exists():
            pytest.skip("sample-repo fixture not found")
        gt = sample_repo / "ground-truth.toml"
        if not gt.exists():
            pytest.skip("ground-truth.toml not found")
        # Run eval first to populate data
        runner.invoke(main, [
            "eval", str(sample_repo),
            "--ground-truth", str(gt), "--db", db_path,
        ])
        # Now check history
        result = runner.invoke(main, [
            "eval-history", "--repo", str(sample_repo), "--db", db_path,
        ])
        assert result.exit_code == 0
        assert "Findings" in result.output
        assert "Prec" in result.output

    def test_eval_history_json_after_eval(self, runner, db_path):
        """Eval history JSON output includes results after running eval."""
        sample_repo = Path(__file__).parent / "fixtures" / "sample-repo"
        if not sample_repo.exists():
            pytest.skip("sample-repo fixture not found")
        gt = sample_repo / "ground-truth.toml"
        if not gt.exists():
            pytest.skip("ground-truth.toml not found")
        # Run eval first
        runner.invoke(main, [
            "eval", str(sample_repo),
            "--ground-truth", str(gt), "--db", db_path,
        ])
        result = runner.invoke(main, [
            "eval-history", "--repo", str(sample_repo), "--db", db_path,
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1
        assert "precision" in data[0]
        assert "recall" in data[0]


# ── version ──────────────────────────────────────────────────────────


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "sentinel" in result.output


# ── quiet mode ───────────────────────────────────────────────────────


class TestQuietMode:
    def test_quiet_flag_accepted(self, runner):
        result = runner.invoke(main, ["-q", "--help"])
        assert result.exit_code == 0

    def test_quiet_suppresses_scan_output(self, runner, test_repo, tmp_path):
        db_path = str(tmp_path / "test.db")
        result = runner.invoke(main, [
            "-q", "scan", str(test_repo),
            "--skip-judge", "--db", db_path,
        ])
        assert result.exit_code == 0
        # Quiet mode should have minimal output (no log lines)
        assert "[INFO]" not in result.output
        assert "[DEBUG]" not in result.output

    def test_verbose_and_quiet_conflict(self, runner):
        result = runner.invoke(main, ["-v", "-q", "history", "--help"])
        assert result.exit_code != 0
        assert "Cannot use --verbose and --quiet together" in result.output
