"""Git hotspots detector — flags files with unusually high churn."""

from __future__ import annotations

import logging
import subprocess
from collections import Counter
from pathlib import Path

from sentinel.detectors.base import Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)

logger = logging.getLogger(__name__)

# Default lookback period (days) for git log
_DEFAULT_DAYS = 90

# Minimum number of commits for a file to be considered a hotspot
_DEFAULT_MIN_COMMITS = 10

# Files with commit counts above (mean + threshold * stdev) are hotspots
_DEFAULT_STDEV_THRESHOLD = 2.0

_SKIP_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".tox", ".sentinel",
})


class GitHotspotsDetector(Detector):
    """Detect files with high git churn that may need extra review attention."""

    @property
    def name(self) -> str:
        return "git-hotspots"

    @property
    def description(self) -> str:
        return "Flags files with unusually high commit frequency (churn hotspots)"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.HEURISTIC

    @property
    def categories(self) -> list[str]:
        return ["git-health"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        repo_root = context.repo_root
        config = context.config

        days = int(config.get("hotspot_days", _DEFAULT_DAYS))
        min_commits = int(config.get("hotspot_min_commits", _DEFAULT_MIN_COMMITS))
        stdev_threshold = float(
            config.get("hotspot_stdev_threshold", _DEFAULT_STDEV_THRESHOLD)
        )

        if not _is_git_repo(repo_root):
            logger.info("Not a git repository, skipping git-hotspots")
            return []

        file_commits, file_authors = _collect_churn(repo_root, days)
        if not file_commits:
            return []

        hotspots = _identify_hotspots(
            file_commits, min_commits, stdev_threshold
        )
        if not hotspots:
            return []

        findings: list[Finding] = []
        for file_path, commit_count in hotspots:
            authors = file_authors.get(file_path, set())
            finding = _build_finding(
                file_path, commit_count, authors, days, repo_root
            )
            findings.append(finding)

        return findings


def _is_git_repo(repo_root: str) -> bool:
    """Check if the path is inside a git repository."""
    return (Path(repo_root) / ".git").is_dir()


def _collect_churn(
    repo_root: str, days: int
) -> tuple[Counter[str], dict[str, set[str]]]:
    """Run git log and count commits per file + collect distinct authors."""
    _COMMIT_SEP = "__SENTINEL_COMMIT__"
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--since={days} days ago",
                f"--pretty=format:{_COMMIT_SEP}%an",
                "--name-only",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("git log failed or timed out")
        return Counter(), {}

    if result.returncode != 0:
        logger.warning("git log returned non-zero: %s", result.stderr[:200])
        return Counter(), {}

    file_commits: Counter[str] = Counter()
    file_authors: dict[str, set[str]] = {}

    current_author = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(_COMMIT_SEP):
            current_author = line[len(_COMMIT_SEP):]
            continue
        if current_author is None:
            continue
        # This line is a file path
        file_path = line
        if _should_skip(file_path):
            continue
        file_commits[file_path] += 1
        file_authors.setdefault(file_path, set()).add(current_author)

    return file_commits, file_authors


def _should_skip(file_path: str) -> bool:
    """Skip files in ignored directories or non-source files."""
    parts = Path(file_path).parts
    return any(part in _SKIP_DIRS for part in parts)


def _identify_hotspots(
    file_commits: Counter[str],
    min_commits: int,
    stdev_threshold: float,
) -> list[tuple[str, int]]:
    """Find files with commit counts significantly above the mean."""
    counts = list(file_commits.values())
    if len(counts) < 2:
        return []

    mean = sum(counts) / len(counts)
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    stdev = variance**0.5

    if stdev < 1.0:
        # Very uniform churn — no meaningful hotspots
        return []

    threshold = mean + stdev_threshold * stdev

    hotspots = [
        (path, count)
        for path, count in file_commits.most_common()
        if count >= max(min_commits, threshold)
    ]

    return hotspots


# File extensions considered documentation (churn is expected, not a risk)
_DOC_EXTENSIONS = frozenset({
    ".md", ".rst", ".txt", ".adoc", ".asciidoc",
})


def _build_finding(
    file_path: str,
    commit_count: int,
    authors: set[str],
    days: int,
    repo_root: str,
) -> Finding:
    """Construct a Finding for a hotspot file."""
    author_str = ", ".join(sorted(authors)[:5])
    if len(authors) > 5:
        author_str += f" (+{len(authors) - 5} more)"

    is_doc_file = Path(file_path).suffix.lower() in _DOC_EXTENSIONS

    severity = Severity.LOW
    if commit_count >= 30 and not is_doc_file:
        severity = Severity.MEDIUM

    confidence = min(0.5 + (commit_count / 100), 0.85)
    # Documentation files naturally churn — reduce confidence significantly
    if is_doc_file:
        confidence = min(confidence, 0.30)

    description = (
        f"This file has been modified {commit_count} times in the last {days} days "
        f"by {len(authors)} author(s). High-churn files are more likely to contain "
        f"regressions, merge conflicts, or accumulated complexity."
    )

    evidence_content = (
        f"Commits: {commit_count} in {days} days\n"
        f"Authors: {author_str}\n"
    )

    # Try to get the file size as additional context
    full_path = Path(repo_root) / file_path
    if full_path.is_file():
        try:
            line_count = len(full_path.read_text(encoding="utf-8", errors="replace").splitlines())
            evidence_content += f"File size: {line_count} lines\n"
        except OSError:
            pass

    return Finding(
        detector="git-hotspots",
        category="git-health",
        severity=severity,
        confidence=round(confidence, 2),
        title=f"High-churn file: {file_path}",
        description=description,
        evidence=[
            Evidence(
                type=EvidenceType.GIT_HISTORY,
                source=file_path,
                content=evidence_content,
            )
        ],
        file_path=file_path,
    )
