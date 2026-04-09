"""Tests for the git-hotspots detector."""

from __future__ import annotations

from collections import Counter

import pytest

from sentinel.detectors.git_hotspots import (
    GitHotspotsDetector,
    _build_finding,
    _identify_hotspots,
    classify_churn,
)
from sentinel.models import DetectorContext, DetectorTier, Severity


@pytest.fixture
def detector():
    return GitHotspotsDetector()


@pytest.fixture
def ctx(tmp_path):
    """Context pointing at a directory (not a git repo by default)."""
    return DetectorContext(repo_root=str(tmp_path), config={})


@pytest.fixture
def git_ctx(tmp_path):
    """Context pointing at a real git repo with some commits."""
    import subprocess

    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )

    # Create a file and commit it many times to make it a hotspot
    hot_file = tmp_path / "hot.py"
    messages = [
        "fix crash on startup",
        "fix null pointer in handler",
        "add logging support",
        "fix regression from last fix",
        "refactor error handling",
        "fix edge case in parser",
        "add retry logic",
        "fix timeout bug",
        "cleanup imports",
        "fix flaky test interaction",
        "hotfix for production crash",
        "fix off-by-one error",
        "add input validation",
        "fix memory leak",
        "patch security issue",
    ]
    for i, msg in enumerate(messages):
        hot_file.write_text(f"# version {i}\nprint('hello')\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(tmp_path), capture_output=True, check=True,
        )

    # Add a stable file with just 1 commit
    stable = tmp_path / "stable.py"
    stable.write_text("# stable\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add stable"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )

    return DetectorContext(
        repo_root=str(tmp_path),
        config={"hotspot_min_commits": 5, "hotspot_stdev_threshold": 1.0},
    )


class TestDetectorProperties:
    def test_name(self, detector):
        assert detector.name == "git-hotspots"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.HEURISTIC

    def test_categories(self, detector):
        assert "git-health" in detector.categories


class TestNotGitRepo:
    def test_returns_empty_for_non_git_dir(self, detector, ctx):
        findings = detector.detect(ctx)
        assert findings == []


class TestIdentifyHotspots:
    def test_no_hotspots_when_uniform(self):
        counts = Counter({"a.py": 5, "b.py": 5, "c.py": 5})
        result = _identify_hotspots(counts, min_commits=3, stdev_threshold=2.0)
        assert result == []

    def test_finds_outlier(self):
        counts = Counter({"hot.py": 50, "a.py": 2, "b.py": 3, "c.py": 1, "d.py": 2})
        result = _identify_hotspots(counts, min_commits=5, stdev_threshold=1.5)
        assert len(result) == 1
        assert result[0][0] == "hot.py"

    def test_respects_min_commits(self):
        counts = Counter({"hot.py": 50, "a.py": 2, "b.py": 3})
        result = _identify_hotspots(counts, min_commits=100, stdev_threshold=1.0)
        assert result == []

    def test_empty_input(self):
        result = _identify_hotspots(Counter(), min_commits=5, stdev_threshold=2.0)
        assert result == []

    def test_single_file(self):
        result = _identify_hotspots(
            Counter({"a.py": 20}), min_commits=5, stdev_threshold=2.0
        )
        assert result == []  # Need at least 2 files for stdev


class TestEndToEnd:
    def test_detects_hotspot_in_real_git_repo(self, detector, git_ctx):
        findings = detector.detect(git_ctx)
        assert len(findings) >= 1
        hot_findings = [f for f in findings if "hot.py" in f.title]
        assert len(hot_findings) == 1
        assert hot_findings[0].detector == "git-hotspots"
        assert hot_findings[0].category == "git-health"
        assert hot_findings[0].file_path == "hot.py"
        assert len(hot_findings[0].evidence) > 0

    def test_stable_file_not_flagged(self, detector, git_ctx):
        findings = detector.detect(git_ctx)
        stable_findings = [f for f in findings if "stable.py" in f.title]
        assert stable_findings == []

    def test_finding_has_evidence(self, detector, git_ctx):
        findings = detector.detect(git_ctx)
        for f in findings:
            assert len(f.evidence) > 0
            assert "Commits:" in f.evidence[0].content
            assert "Authors:" in f.evidence[0].content

    def test_finding_has_commit_types(self, detector, git_ctx):
        """Enriched findings include commit type classification."""
        findings = detector.detect(git_ctx)
        hot_findings = [f for f in findings if "hot.py" in f.title]
        assert len(hot_findings) == 1
        evidence = hot_findings[0].evidence[0].content
        assert "Commit types:" in evidence

    def test_finding_description_has_insight(self, detector, git_ctx):
        """Enriched description explains *why* churn matters."""
        findings = detector.detect(git_ctx)
        hot_findings = [f for f in findings if "hot.py" in f.title]
        assert len(hot_findings) == 1
        desc = hot_findings[0].description
        # The fixture is bug-fix heavy, so the insight should mention that
        assert "bug-fix" in desc.lower() or "fragile" in desc.lower() or "pattern" in desc.lower()


class TestChurnClassification:
    """Tests for commit message classification."""

    def test_fix_heavy(self):
        messages = ["fix crash", "fix null", "fix timeout", "add feature", "cleanup"]
        result = classify_churn(messages)
        assert result["fix"] == 3
        assert result["feature"] == 1
        assert result["refactor"] == 1

    def test_refactor_heavy(self):
        messages = ["refactor auth", "rename handler", "restructure module", "extract util"]
        result = classify_churn(messages)
        assert result["refactor"] == 4
        assert result["fix"] == 0

    def test_feature_heavy(self):
        messages = ["add user model", "implement search", "feat: dark mode", "new endpoint"]
        result = classify_churn(messages)
        assert result["feature"] == 4

    def test_empty_messages(self):
        result = classify_churn([])
        assert result == {"fix": 0, "refactor": 0, "feature": 0, "other": 0}

    def test_unclassifiable_messages(self):
        messages = ["update version", "bump deps", "WIP"]
        result = classify_churn(messages)
        assert result["other"] == 3

    def test_mixed_messages(self):
        messages = ["fix bug", "add feature", "refactor code", "bump version"]
        result = classify_churn(messages)
        assert result == {"fix": 1, "feature": 1, "refactor": 1, "other": 1}


class TestDocFileHandling:
    """Documentation files should get reduced confidence/severity."""

    def test_doc_file_capped_at_low_severity(self, tmp_path):
        """Even high-churn .md files should stay LOW, not escalate to MEDIUM."""
        readme = tmp_path / "README.md"
        readme.write_text("# Hello\n")
        finding = _build_finding(
            "README.md", 50, {"Alice"}, ["update docs"] * 50, 90, str(tmp_path),
        )
        assert finding.severity == Severity.LOW

    def test_doc_file_confidence_capped(self, tmp_path):
        """Doc files should have low confidence (churn is expected)."""
        readme = tmp_path / "README.md"
        readme.write_text("# Hello\n")
        finding = _build_finding(
            "README.md", 50, {"Alice"}, ["update docs"] * 50, 90, str(tmp_path),
        )
        assert finding.confidence <= 0.30

    def test_code_file_normal_severity(self, tmp_path):
        """Code files with high churn should escalate to MEDIUM normally."""
        code = tmp_path / "app.py"
        code.write_text("x = 1\n")
        finding = _build_finding(
            "app.py", 50, {"Alice"}, ["add feature"] * 50, 90, str(tmp_path),
        )
        assert finding.severity == Severity.MEDIUM
        assert finding.confidence > 0.30


class TestBugFixEscalation:
    """Bug-fix-heavy churn should increase severity and confidence."""

    def test_fix_heavy_escalates_medium_at_15_commits(self, tmp_path):
        code = tmp_path / "handler.py"
        code.write_text("def handle(): pass\n")
        # 15 commits, >50% fixes → should escalate to MEDIUM
        messages = ["fix bug"] * 10 + ["add feature"] * 5
        finding = _build_finding(
            "handler.py", 15, {"Alice", "Bob"}, messages, 90, str(tmp_path),
        )
        assert finding.severity == Severity.MEDIUM

    def test_feature_heavy_stays_low_at_15_commits(self, tmp_path):
        code = tmp_path / "handler.py"
        code.write_text("def handle(): pass\n")
        # 15 commits, mostly features → stays LOW
        messages = ["add feature"] * 12 + ["fix bug"] * 3
        finding = _build_finding(
            "handler.py", 15, {"Alice"}, messages, 90, str(tmp_path),
        )
        assert finding.severity == Severity.LOW

    def test_fix_heavy_boosts_confidence(self, tmp_path):
        code = tmp_path / "fragile.py"
        code.write_text("x = 1\n")
        fix_messages = ["fix crash"] * 8 + ["add feature"] * 2
        feat_messages = ["add feature"] * 8 + ["fix crash"] * 2
        fix_finding = _build_finding(
            "fragile.py", 10, {"Alice"}, fix_messages, 90, str(tmp_path),
        )
        feat_finding = _build_finding(
            "fragile.py", 10, {"Alice"}, feat_messages, 90, str(tmp_path),
        )
        assert fix_finding.confidence > feat_finding.confidence


class TestAuthorInsights:
    """Author concentration should be reflected in descriptions."""

    def test_single_author_bus_factor(self, tmp_path):
        code = tmp_path / "solo.py"
        code.write_text("x = 1\n")
        finding = _build_finding(
            "solo.py", 20, {"Alice"}, ["update"] * 20, 90, str(tmp_path),
        )
        assert "bus-factor" in finding.description.lower()

    def test_many_authors_coordination(self, tmp_path):
        code = tmp_path / "shared.py"
        code.write_text("x = 1\n")
        authors = {"Alice", "Bob", "Charlie", "Diana", "Eve"}
        finding = _build_finding(
            "shared.py", 20, authors, ["update"] * 20, 90, str(tmp_path),
        )
        assert "coordination" in finding.description.lower()
