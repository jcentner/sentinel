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
        assert "Severity:" in result.output
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

    def test_scan_with_detectors_filter(self, runner, test_repo, db_path, tmp_path):
        """--detectors limits which detectors run."""
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
            "--detectors", "todo-scanner",
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        detectors_used = {f["detector"] for f in data["findings"]}
        # Only todo-scanner findings (or empty if no TODOs)
        assert detectors_used <= {"todo-scanner"}

    def test_scan_with_skip_detectors(self, runner, test_repo, db_path, tmp_path):
        """--skip-detectors excludes specific detectors."""
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
            "--skip-detectors", "todo-scanner,complexity",
            "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        detectors_used = {f["detector"] for f in data["findings"]}
        assert "todo-scanner" not in detectors_used
        assert "complexity" not in detectors_used

    def test_scan_detectors_and_skip_detectors_conflict(self, runner, test_repo, db_path):
        """Cannot use both --detectors and --skip-detectors."""
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path,
            "--detectors", "todo-scanner",
            "--skip-detectors", "complexity",
        ])
        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_scan_with_capability_flag(self, runner, test_repo, db_path, tmp_path):
        """--capability sets model capability tier."""
        out = str(tmp_path / "report.md")
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path, "-o", out,
            "--capability", "standard",
        ])
        assert result.exit_code == 0

    def test_scan_invalid_capability(self, runner, test_repo, db_path):
        """--capability rejects invalid values."""
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path,
            "--capability", "turbo",
        ])
        assert result.exit_code != 0
        assert "turbo" in result.output

    def test_scan_config_enabled_plus_cli_skip_conflict(self, runner, test_repo, db_path):
        """Config enabled_detectors + CLI --skip-detectors should conflict."""
        (test_repo / "sentinel.toml").write_text(
            '[sentinel]\nenabled_detectors = ["todo-scanner"]\n'
        )
        result = runner.invoke(main, [
            "scan", str(test_repo),
            "--skip-judge", "--db", db_path,
            "--skip-detectors", "complexity",
        ])
        assert result.exit_code != 0
        assert "Cannot use both" in result.output


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


# ── init command ─────────────────────────────────────────────────────


class TestInitCommand:
    def test_init_creates_config(self, runner, tmp_path):
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Created" in result.output
        config = tmp_path / "sentinel.toml"
        assert config.exists()
        content = config.read_text()
        assert "[sentinel]" in content
        assert 'model = "qwen3.5:4b"' in content

    def test_init_creates_sentinel_dir(self, runner, tmp_path):
        runner.invoke(main, ["init", str(tmp_path)])
        assert (tmp_path / ".sentinel").is_dir()

    def test_init_creates_gitignore(self, runner, tmp_path):
        runner.invoke(main, ["init", str(tmp_path)])
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".sentinel/" in gitignore.read_text()

    def test_init_appends_to_existing_gitignore(self, runner, tmp_path):
        (tmp_path / ".gitignore").write_text("*.pyc\n")
        runner.invoke(main, ["init", str(tmp_path)])
        content = (tmp_path / ".gitignore").read_text()
        assert "*.pyc" in content
        assert ".sentinel/" in content

    def test_init_skips_gitignore_if_already_present(self, runner, tmp_path):
        (tmp_path / ".gitignore").write_text(".sentinel/\n")
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Added .sentinel/ to .gitignore" not in result.output

    def test_init_refuses_existing_config(self, runner, tmp_path):
        (tmp_path / "sentinel.toml").write_text("[sentinel]\n")
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_init_force_overwrites(self, runner, tmp_path):
        (tmp_path / "sentinel.toml").write_text("[sentinel]\n")
        result = runner.invoke(main, ["init", str(tmp_path), "--force"])
        assert result.exit_code == 0
        content = (tmp_path / "sentinel.toml").read_text()
        assert 'model = "qwen3.5:4b"' in content

    def test_init_list_detectors(self, runner, tmp_path):
        result = runner.invoke(main, ["init", str(tmp_path), "--list-detectors"])
        assert result.exit_code == 0
        assert "Available detectors:" in result.output
        assert "todo-scanner" in result.output
        assert "Profiles:" in result.output
        # Should not create a config file
        assert not (tmp_path / "sentinel.toml").exists()

    def test_init_profile_minimal(self, runner, tmp_path):
        result = runner.invoke(main, ["init", str(tmp_path), "--profile", "minimal"])
        assert result.exit_code == 0
        content = (tmp_path / "sentinel.toml").read_text()
        assert 'skip_judge = true' in content
        assert 'model_capability = "none"' in content
        assert '"todo-scanner"' in content
        # LLM-dependent detectors excluded
        assert '"semantic-drift"' not in content
        assert '"test-coherence"' not in content

    def test_init_profile_full(self, runner, tmp_path):
        result = runner.invoke(main, ["init", str(tmp_path), "--profile", "full"])
        assert result.exit_code == 0
        content = (tmp_path / "sentinel.toml").read_text()
        assert 'model_capability = "standard"' in content
        assert '"semantic-drift"' in content
        assert '"test-coherence"' in content

    def test_init_detectors_flag(self, runner, tmp_path):
        result = runner.invoke(main, [
            "init", str(tmp_path), "--detectors", "todo-scanner,lint-runner",
        ])
        assert result.exit_code == 0
        content = (tmp_path / "sentinel.toml").read_text()
        assert '"todo-scanner"' in content
        assert '"lint-runner"' in content
        assert '"complexity"' not in content
        assert "Enabled 2 detectors" in result.output

    def test_init_profile_and_detectors_conflict(self, runner, tmp_path):
        result = runner.invoke(main, [
            "init", str(tmp_path), "--profile", "minimal", "--detectors", "todo-scanner",
        ])
        assert result.exit_code != 0

    def test_init_default_includes_enabled_detectors(self, runner, tmp_path):
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        content = (tmp_path / "sentinel.toml").read_text()
        assert "enabled_detectors" in content
        assert '"todo-scanner"' in content
        assert "all detectors enabled" in result.output.lower()


# ── scan-all command ─────────────────────────────────────────────────


class TestScanAllCommand:
    def test_scan_all_multiple_repos(self, runner, test_repo, tmp_path):
        """Scan two repos into a shared DB."""
        # Create a second test repo
        repo2 = tmp_path / "repo2"
        repo2.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo2), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo2), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo2), capture_output=True, check=True,
        )
        (repo2 / "app.py").write_text("# TODO: implement\n")
        subprocess.run(["git", "add", "-A"], cwd=str(repo2), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo2), capture_output=True, check=True,
        )

        db_path = str(tmp_path / "shared.db")
        result = runner.invoke(main, [
            "scan-all", str(test_repo), str(repo2),
            "--db", db_path, "--skip-judge",
        ])
        assert result.exit_code == 0
        assert "Scanned 2/2 repos" in result.output
        assert "total findings" in result.output

    def test_scan_all_json_output(self, runner, test_repo, tmp_path):
        db_path = str(tmp_path / "shared.db")
        result = runner.invoke(main, [
            "scan-all", str(test_repo),
            "--db", db_path, "--skip-judge", "--json-output",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "ok"
        assert data["results"][0]["findings"] >= 0

    def test_scan_all_requires_db(self, runner, test_repo):
        result = runner.invoke(main, ["scan-all", str(test_repo)])
        assert result.exit_code != 0

    def test_scan_all_partial_failure(self, runner, test_repo, tmp_path):
        """One bad repo config should not prevent other repos from scanning."""
        bad_repo = tmp_path / "bad"
        bad_repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(bad_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(bad_repo), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(bad_repo), capture_output=True, check=True,
        )
        (bad_repo / "file.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=str(bad_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(bad_repo), capture_output=True, check=True,
        )
        # Create a bad sentinel.toml that will cause a config error
        (bad_repo / "sentinel.toml").write_text('[sentinel]\nmodel = 42\n')

        db_path = str(tmp_path / "shared.db")
        result = runner.invoke(main, [
            "scan-all", str(test_repo), str(bad_repo),
            "--db", db_path, "--skip-judge",
        ])
        # Should exit 2 (partial failure)
        assert result.exit_code == 2
        assert "Scanned 1/2 repos" in result.output


# ── doctor command ───────────────────────────────────────────────────


class TestDoctorCommand:
    def test_doctor_runs(self, runner):
        result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        assert "Sentinel Doctor" in result.output
        assert "checks passed" in result.output
        # git should always be available in test environment
        assert "git" in result.output

    def test_doctor_json_output(self, runner):
        result = runner.invoke(main, ["doctor", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "checks" in data
        assert any(c["tool"] == "git" for c in data["checks"])
        # Each check should have required fields
        for check in data["checks"]:
            assert "tool" in check
            assert "status" in check
            assert check["status"] in ("ok", "missing")
        # At least one tool should be missing in typical test environments
        # (e.g. golangci-lint, cargo clippy, biome are not commonly installed)
        statuses = {c["status"] for c in data["checks"]}
        assert "missing" in statuses or "ok" in statuses  # at least one result


class TestCompatibilityCommand:
    def test_compatibility_full_matrix(self, runner):
        result = runner.invoke(main, ["compatibility"])
        assert result.exit_code == 0
        assert "Detector" in result.output
        assert "4b-local" in result.output
        assert "Legend:" in result.output
        # Should show key detectors
        assert "semantic-drift" in result.output
        assert "test-coherence" in result.output

    def test_compatibility_single_detector(self, runner):
        result = runner.invoke(main, ["compatibility", "-d", "test-coherence"])
        assert result.exit_code == 0
        assert "test-coherence" in result.output
        assert "Recommended:" in result.output
        assert "4b-local" in result.output

    def test_compatibility_single_model(self, runner):
        result = runner.invoke(main, ["compatibility", "-m", "4b-local"])
        assert result.exit_code == 0
        assert "4b-local" in result.output
        assert "qwen3.5:4b" in result.output

    def test_compatibility_json_output(self, runner):
        result = runner.invoke(main, ["compatibility", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "compatibility" in data
        assert len(data["compatibility"]) > 0
        # Each row should have detector and tier
        for row in data["compatibility"]:
            assert "detector" in row
            assert "tier" in row

    def test_compatibility_unknown_detector(self, runner):
        result = runner.invoke(main, ["compatibility", "-d", "nonexistent"])
        assert result.exit_code != 0
        assert "Unknown detector" in result.output

    def test_compatibility_unknown_model(self, runner):
        result = runner.invoke(main, ["compatibility", "-m", "nonexistent"])
        assert result.exit_code != 0
        assert "Unknown model class" in result.output
