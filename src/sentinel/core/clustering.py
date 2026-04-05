"""Finding clustering — groups related findings to reduce report noise.

Clusters findings that share the same detector, category, and parent
directory.  A cluster of 3+ findings collapses into one summary line
in the morning report, keeping it scannable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from sentinel.models import Finding

# Minimum number of findings to form a cluster
MIN_CLUSTER_SIZE = 3


@dataclass(frozen=True)
class FindingCluster:
    """A group of related findings sharing a common directory."""

    common_path: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def label(self) -> str:
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
