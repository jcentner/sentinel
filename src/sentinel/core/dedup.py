"""Finding fingerprinting and deduplication."""

from __future__ import annotations

import hashlib
import re
import sqlite3

from sentinel.models import Finding
from sentinel.store.findings import (
    get_known_fingerprints,
    get_known_fuzzy_fingerprints,
    get_suppressed_fingerprints,
)


def compute_fingerprint(finding: Finding) -> str:
    """Compute a content-based fingerprint for deduplication.

    Hash is based on (detector, category, effective_file_path, normalized_content)
    so that line number shifts don't break dedup.  For docs-drift stale
    references the effective path is the *target*, not the source doc.
    """
    content = _normalize_content(finding)
    file_path = _effective_file_path(finding)
    raw = f"{finding.detector}:{finding.category}:{file_path}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_fuzzy_fingerprint(finding: Finding) -> str:
    """Compute a path-free fingerprint for cross-rename recurrence (TD-031).

    Uses (detector, category, normalized_content) — same as strict fingerprint
    but omitting file_path. This allows detecting that a finding is recurring
    even after a file rename.
    """
    content = _normalize_content(finding, include_path=False)
    raw = f"{finding.detector}:{finding.category}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def assign_fingerprints(findings: list[Finding]) -> list[Finding]:
    """Assign fingerprints to all findings that don't have one yet."""
    for f in findings:
        if not f.fingerprint:
            f.fingerprint = compute_fingerprint(f)
        if not f.fuzzy_fingerprint:
            f.fuzzy_fingerprint = compute_fuzzy_fingerprint(f)
    return findings


def deduplicate(
    findings: list[Finding],
    conn: sqlite3.Connection,
) -> list[Finding]:
    """Filter out findings that are suppressed or already seen in prior runs.

    Returns only new or recurring findings that should appear in the report.
    """
    suppressed = get_suppressed_fingerprints(conn)
    known = get_known_fingerprints(conn)
    known_fuzzy = get_known_fuzzy_fingerprints(conn)

    result: list[Finding] = []
    seen_this_run: set[str] = set()

    for f in findings:
        fp = f.fingerprint
        # Skip suppressed
        if fp in suppressed:
            continue
        # Skip duplicate within same run
        if fp in seen_this_run:
            continue
        seen_this_run.add(fp)
        # Mark as new vs. recurring
        f.context = f.context or {}
        if fp in known:
            f.context["recurring"] = True
        elif f.fuzzy_fingerprint in known_fuzzy:
            # Fuzzy match: same finding, different path (file renamed)
            f.context["recurring"] = True
            f.context["fuzzy_match"] = True
        result.append(f)

    return result


def _normalize_content(finding: Finding, *, include_path: bool = True) -> str:
    """Normalize content for fingerprinting — strip noise, keep signal.

    When include_path=False (fuzzy mode), excludes file_path from content
    so the fingerprint survives file renames.
    """
    # Use the title as primary content signal (it captures the essence)
    content = finding.title

    # For dep-audit, include the vuln ID which is stable
    if finding.context and "vuln_id" in finding.context:
        content = f"{finding.context['vuln_id']}:{finding.context.get('package', '')}"

    # For lint-runner, include the rule code and title for uniqueness
    if finding.context and "rule" in finding.context:
        if include_path:
            content = f"{finding.context['rule']}:{finding.file_path or ''}:{finding.title}"
        else:
            content = f"{finding.context['rule']}:{finding.title}"

    # Normalize whitespace
    content = re.sub(r"\s+", " ", content).strip().lower()
    return content


def _effective_file_path(finding: Finding) -> str:
    """Return the file path to use for fingerprinting.

    For docs-drift stale references, the finding's file_path is the *source*
    doc containing the broken reference, but the *target* (referenced_path or
    link target) is what identifies the issue.  Multiple docs referencing the
    same missing file should be deduped into a single finding.
    """
    if finding.context:
        pattern = finding.context.get("pattern", "")
        if pattern in ("stale-inline-path", "stale-reference"):
            target = finding.context.get("referenced_path") or finding.context.get("target")
            if target:
                return str(target)
    return finding.file_path or ""
