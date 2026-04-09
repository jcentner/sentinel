"""Git hotspots detector — flags files with unusually high churn.

Enriched with commit-message analysis to classify *why* a file is churning
(bug-fix heavy, refactor heavy, feature-add heavy) and author concentration
to flag bus-factor risk.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections import Counter
from pathlib import Path

from sentinel.detectors.base import COMMON_SKIP_DIRS, Detector
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

_SKIP_DIRS = COMMON_SKIP_DIRS

# ── Commit message classification patterns ─────────────────────────

_FIX_PATTERNS = re.compile(
    r"\b(fix|bug|patch|hotfix|revert|regression|broke|crash|error|issue)\b",
    re.IGNORECASE,
)
_REFACTOR_PATTERNS = re.compile(
    r"\b(refactor|rename|restructure|reorganize|cleanup|clean[- ]?up|simplif|extract|move)\b",
    re.IGNORECASE,
)
_FEATURE_PATTERNS = re.compile(
    r"\b(feat|feature|add|implement|introduce|new|support|enable)\b",
    re.IGNORECASE,
)


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
        try:
            return self._scan(context)
        except Exception:
            logger.exception("git-hotspots failed")
            return []

    def _scan(self, context: DetectorContext) -> list[Finding]:
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

        churn = _collect_churn(repo_root, days)
        if not churn:
            return []

        file_commits: Counter[str] = Counter(
            {path: data.commits for path, data in churn.items()}
        )

        hotspots = _identify_hotspots(
            file_commits, min_commits, stdev_threshold
        )
        if not hotspots:
            return []

        findings: list[Finding] = []
        for file_path, commit_count in hotspots:
            data = churn[file_path]
            finding = _build_finding(
                file_path, commit_count, data.authors, data.messages,
                days, repo_root,
            )
            findings.append(finding)

        return findings


def _is_git_repo(repo_root: str) -> bool:
    """Check if the path is inside a git repository."""
    return (Path(repo_root) / ".git").is_dir()


class _ChurnData:
    """Aggregated churn data for a single file."""

    __slots__ = ("authors", "commits", "messages")

    def __init__(self) -> None:
        self.commits: int = 0
        self.authors: set[str] = set()
        self.messages: list[str] = []


def _collect_churn(
    repo_root: str, days: int
) -> dict[str, _ChurnData]:
    """Run git log and collect per-file commit stats + messages."""
    _COMMIT_SEP = "__SENTINEL_COMMIT__"
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--since={days} days ago",
                f"--pretty=format:{_COMMIT_SEP}%an\t%s",
                "--name-only",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("git log failed or timed out")
        return {}

    if result.returncode != 0:
        logger.warning("git log returned non-zero: %s", result.stderr[:200])
        return {}

    churn: dict[str, _ChurnData] = {}

    current_author: str | None = None
    current_message: str = ""
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(_COMMIT_SEP):
            parts = line[len(_COMMIT_SEP):].split("\t", 1)
            current_author = parts[0]
            current_message = parts[1] if len(parts) > 1 else ""
            continue
        if current_author is None:
            continue
        # This line is a file path
        file_path = line
        if _should_skip(file_path):
            continue
        data = churn.get(file_path)
        if data is None:
            data = _ChurnData()
            churn[file_path] = data
        data.commits += 1
        data.authors.add(current_author)
        data.messages.append(current_message)

    return churn


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


def classify_churn(messages: list[str]) -> dict[str, int]:
    """Classify commit messages into churn categories.

    Returns counts for: fix, refactor, feature, other.
    """
    counts: dict[str, int] = {"fix": 0, "refactor": 0, "feature": 0, "other": 0}
    for msg in messages:
        if _FIX_PATTERNS.search(msg):
            counts["fix"] += 1
        elif _REFACTOR_PATTERNS.search(msg):
            counts["refactor"] += 1
        elif _FEATURE_PATTERNS.search(msg):
            counts["feature"] += 1
        else:
            counts["other"] += 1
    return counts


def _churn_insight(categories: dict[str, int], total: int) -> str:
    """Produce a human-readable churn insight from classified messages."""
    if total == 0:
        return "No commit messages to analyze."

    dominant = max(categories, key=lambda k: categories[k])
    pct = round(100 * categories[dominant] / total)

    insights = {
        "fix": (
            f"{pct}% of commits are bug-fixes or patches — this file may be "
            f"fragile or poorly tested. Consider adding targeted tests."
        ),
        "refactor": (
            f"{pct}% of commits are refactoring/restructuring — this file may "
            f"be accumulating complexity that warrants decomposition."
        ),
        "feature": (
            f"{pct}% of commits add features — active development area. "
            f"Verify test coverage is keeping pace."
        ),
        "other": (
            "Commit messages don't indicate a clear pattern. "
            "Review git log for this file to understand the churn."
        ),
    }
    # Only emphasize the pattern if it's meaningfully dominant (>40%)
    if pct <= 40:
        return (
            "Churn is mixed across categories (no dominant pattern). "
            "Review git log for this file to understand the churn."
        )
    return insights[dominant]


def _build_finding(
    file_path: str,
    commit_count: int,
    authors: set[str],
    messages: list[str],
    days: int,
    repo_root: str,
) -> Finding:
    """Construct a Finding for a hotspot file."""
    author_str = ", ".join(sorted(authors)[:5])
    if len(authors) > 5:
        author_str += f" (+{len(authors) - 5} more)"

    is_doc_file = Path(file_path).suffix.lower() in _DOC_EXTENSIONS

    # Classify commit messages
    categories = classify_churn(messages)

    # Severity: escalate if high-churn + bug-fix heavy
    severity = Severity.LOW
    if not is_doc_file:
        fix_ratio = categories["fix"] / max(commit_count, 1)
        if commit_count >= 30 or (commit_count >= 15 and fix_ratio > 0.5):
            severity = Severity.MEDIUM

    confidence = min(0.5 + (commit_count / 100), 0.85)
    # Bug-fix-heavy churn increases confidence (it's a real signal)
    if categories["fix"] > categories["feature"] and categories["fix"] >= 3:
        confidence = min(confidence + 0.1, 0.90)
    # Documentation files naturally churn — reduce confidence significantly
    if is_doc_file:
        confidence = min(confidence, 0.30)

    # Build actionable description
    insight = _churn_insight(categories, commit_count)
    author_note = ""
    if len(authors) == 1:
        author_note = (
            " Only one author has touched this file — potential bus-factor risk."
        )
    elif len(authors) >= 5:
        author_note = (
            f" {len(authors)} distinct authors — high coordination overhead."
        )

    description = (
        f"This file has been modified {commit_count} times in the last {days} days "
        f"by {len(authors)} author(s). {insight}{author_note}"
    )

    # Build detailed evidence
    cat_str = ", ".join(
        f"{k}: {v}" for k, v in sorted(categories.items()) if v > 0
    )
    evidence_content = (
        f"Commits: {commit_count} in {days} days\n"
        f"Authors: {author_str}\n"
        f"Commit types: {cat_str}\n"
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
