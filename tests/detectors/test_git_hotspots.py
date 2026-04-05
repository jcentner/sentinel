"""Tests for the git-hotspots detector."""

from __future__ import annotations

from collections import Counter

import pytest

from sentinel.detectors.git_hotspots import (
    GitHotspotsDetector,
    _identify_hotspots,
)
from sentinel.models import DetectorContext, DetectorTier


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
    for i in range(15):
        hot_file.write_text(f"# version {i}\nprint('hello')\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"change {i}", "--allow-empty-message"],
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
