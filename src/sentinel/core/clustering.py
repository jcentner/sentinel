"""Finding clustering — groups related findings to reduce report noise.

Clusters findings that share a parent directory, or the same detector +
title pattern.  A cluster of 3+ findings collapses into one summary
line in the morning report, keeping it scannable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from sentinel.models import Finding

# Minimum number of findings to form a cluster
MIN_CLUSTER_SIZE = 3

# Regex to strip file-specific details from titles for pattern matching
_FILE_SPECIFIC = re.compile(
    r"""
    \b(?:in|at|from)\s+`?[\w./\\-]+`?    # "in `foo/bar.py`"
    | (?::\s*\d+)                         # ":42" line numbers
    | \s*\([^)]{1,60}\)\s*$               # trailing parenthetical
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class FindingCluster:
    """A group of related findings sharing a common trait."""

    common_path: str
    findings: list[Finding] = field(default_factory=list)
    cluster_type: str = "directory"   # "directory" or "pattern"
    pattern_label: str = ""           # human-readable label for pattern clusters

    @property
    def label(self) -> str:
        if self.cluster_type == "pattern" and self.pattern_label:
            return f"{len(self.findings)} related: {self.pattern_label}"
        n = len(self.findings)
        path = self.common_path or "(no file)"
        return f"{n} findings in `{path}`"


def cluster_findings(
    findings: list[Finding],
    min_size: int = MIN_CLUSTER_SIZE,
) -> list[Finding | FindingCluster]:
    """Cluster related findings by parent directory.

    Findings with the same parent directory are grouped.  Groups with
    fewer than *min_size* members are returned as individual findings.

    Returns a mixed list of standalone ``Finding`` objects and
    ``FindingCluster`` objects, ordered: clusters first (largest first),
    then standalone findings.
    """
    if not findings or min_size < 2:
        return list(findings)

    # Group by parent directory of file_path
    buckets: dict[str, list[Finding]] = {}
    for f in findings:
        dir_key = str(PurePosixPath(f.file_path).parent) if f.file_path else ""
        buckets.setdefault(dir_key, []).append(f)

    clusters: list[FindingCluster] = []
    standalone: list[Finding] = []

    for dir_path, group in buckets.items():
        if len(group) >= min_size:
            clusters.append(FindingCluster(common_path=dir_path, findings=group))
        else:
            standalone.extend(group)

    # Sort clusters by size descending, then standalone as-is
    clusters.sort(key=lambda c: len(c.findings), reverse=True)

    result: list[Finding | FindingCluster] = []
    result.extend(clusters)
    result.extend(standalone)
    return result


def _normalize_title(title: str) -> str:
    """Strip file-specific details from a title for pattern grouping.

    >>> _normalize_title("[unused] func `helper` is unused")
    '[unused] func  is unused'
    >>> _normalize_title("TODO found in `src/main.py`:42")
    'TODO found'
    """
    return _FILE_SPECIFIC.sub("", title).strip()


def cluster_by_pattern(
    findings: list[Finding],
    min_size: int = MIN_CLUSTER_SIZE,
) -> list[Finding | FindingCluster]:
    """Cluster findings by detector + normalized title pattern.

    Findings from the same detector whose titles differ only in
    file-specific details (paths, line numbers) are grouped together.
    This catches root-cause scenarios like "renamed dir → N stale links."

    Returns clusters (largest first) then standalone findings.
    """
    if not findings or min_size < 2:
        return list(findings)

    # Group by (detector, normalized_title)
    buckets: dict[tuple[str, str], list[Finding]] = {}
    for f in findings:
        key = (f.detector, _normalize_title(f.title))
        buckets.setdefault(key, []).append(f)

    clusters: list[FindingCluster] = []
    standalone: list[Finding] = []

    for (detector, pattern), group in buckets.items():
        if len(group) >= min_size:
            # Use a readable label from the first finding's normalized title
            label = f"{detector}: {pattern}" if pattern else detector
            clusters.append(FindingCluster(
                common_path="",
                findings=group,
                cluster_type="pattern",
                pattern_label=label,
            ))
        else:
            standalone.extend(group)

    clusters.sort(key=lambda c: len(c.findings), reverse=True)

    result: list[Finding | FindingCluster] = []
    result.extend(clusters)
    result.extend(standalone)
    return result
