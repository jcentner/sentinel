"""GitHub issue creation from approved findings."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from dataclasses import dataclass

from sentinel.models import Finding, FindingStatus
from sentinel.store.findings import get_finding_by_id, update_finding_status

logger = logging.getLogger(__name__)


@dataclass
class GitHubConfig:
    """GitHub integration settings."""

    owner: str
    repo: str
    token: str


@dataclass
class IssueResult:
    """Result of an issue creation attempt."""

    finding_id: int
    fingerprint: str
    success: bool
    issue_url: str | None = None
    error: str | None = None


# Valid GitHub owner/repo names: alphanumeric, hyphens, dots, underscores
_GITHUB_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def _validate_github_name(value: str, label: str) -> None:
    """Validate a GitHub owner or repo name to prevent path traversal."""
    if not _GITHUB_NAME_RE.match(value):
        raise ValueError(
            f"Invalid GitHub {label}: {value!r}. "
            f"Must contain only alphanumeric characters, hyphens, dots, or underscores."
        )


def get_github_config(
    owner: str | None = None,
    repo: str | None = None,
    token: str | None = None,
) -> GitHubConfig | None:
    """Resolve GitHub config from arguments or environment variables.

    Returns None if required fields are missing.
    Raises ValueError if owner or repo contain invalid characters.
    """
    resolved_owner = owner or os.environ.get("SENTINEL_GITHUB_OWNER", "")
    resolved_repo = repo or os.environ.get("SENTINEL_GITHUB_REPO", "")
    resolved_token = token or os.environ.get("SENTINEL_GITHUB_TOKEN", "")

    if not resolved_owner or not resolved_repo or not resolved_token:
        return None

    _validate_github_name(resolved_owner, "owner")
    _validate_github_name(resolved_repo, "repo")

    return GitHubConfig(
        owner=resolved_owner,
        repo=resolved_repo,
        token=resolved_token,
    )


def get_approved_findings(conn: sqlite3.Connection) -> list[tuple[int, Finding]]:
    """Retrieve all findings with APPROVED status, returning (db_id, finding) pairs."""
    rows = conn.execute(
        "SELECT id FROM findings WHERE status = ?", (FindingStatus.APPROVED.value,)
    ).fetchall()

    results = []
    for row in rows:
        finding = get_finding_by_id(conn, row["id"])
        if finding is not None:
            results.append((row["id"], finding))
    return results


def create_issues(
    conn: sqlite3.Connection,
    github: GitHubConfig,
    *,
    dry_run: bool = False,
) -> list[IssueResult]:
    """Create GitHub issues for all approved findings.

    Returns a list of IssueResult indicating success/failure for each.
    Marks successfully created findings as RESOLVED.
    """
    import httpx

    approved = get_approved_findings(conn)
    if not approved:
        logger.info("No approved findings to create issues for")
        return []

    # Check for existing sentinel-created issues to avoid duplicates
    existing_fingerprints = _get_existing_issue_fingerprints(github)

    results: list[IssueResult] = []
    for db_id, finding in approved:
        if finding.fingerprint in existing_fingerprints:
            logger.info(
                "Skipping %s — issue already exists for fingerprint %s",
                finding.title,
                finding.fingerprint,
            )
            results.append(IssueResult(
                finding_id=db_id,
                fingerprint=finding.fingerprint,
                success=True,
                issue_url=existing_fingerprints[finding.fingerprint],
                error="Issue already exists",
            ))
            update_finding_status(conn, db_id, FindingStatus.RESOLVED)
            continue

        if dry_run:
            logger.info("[DRY RUN] Would create issue: %s", finding.title)
            results.append(IssueResult(
                finding_id=db_id,
                fingerprint=finding.fingerprint,
                success=True,
                error="dry run",
            ))
            continue

        title, body = _format_issue(finding)

        try:
            url = f"https://api.github.com/repos/{github.owner}/{github.repo}/issues"
            resp = httpx.post(
                url,
                json={
                    "title": title,
                    "body": body,
                    "labels": _issue_labels(finding),
                },
                headers={
                    "Authorization": f"Bearer {github.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30,
            )
            resp.raise_for_status()
            issue_data = resp.json()
            issue_url = issue_data.get("html_url", "")

            update_finding_status(conn, db_id, FindingStatus.RESOLVED)
            results.append(IssueResult(
                finding_id=db_id,
                fingerprint=finding.fingerprint,
                success=True,
                issue_url=issue_url,
            ))
            logger.info("Created issue: %s → %s", finding.title, issue_url)

        except Exception as exc:
            logger.error("Failed to create issue for %s: %s", finding.title, exc)
            results.append(IssueResult(
                finding_id=db_id,
                fingerprint=finding.fingerprint,
                success=False,
                error=str(exc),
            ))

    return results


def _get_existing_issue_fingerprints(
    github: GitHubConfig,
) -> dict[str, str]:
    """Check open GitHub issues for sentinel fingerprint markers.

    Returns a dict of fingerprint → issue URL for existing sentinel issues.
    """
    import httpx

    try:
        url = (
            f"https://api.github.com/repos/{github.owner}/{github.repo}/issues"
            "?state=open&labels=sentinel&per_page=100"
        )
        resp = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {github.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except Exception:
        logger.warning("Could not fetch existing issues for dedup check")
        return {}

    issues = resp.json()
    if len(issues) >= 100:
        logger.warning(
            "Fetched 100 issues (API page limit) — dedup may be incomplete. "
            "Consider closing resolved sentinel issues on GitHub."
        )

    fingerprints: dict[str, str] = {}
    for issue in issues:
        body = issue.get("body", "") or ""
        match = re.search(r"<!-- sentinel:fingerprint:(\w+) -->", body)
        if match:
            fingerprints[match.group(1)] = issue.get("html_url", "")

    return fingerprints


def _format_issue(finding: Finding) -> tuple[str, str]:
    """Format a finding as a GitHub issue title and body."""
    title = f"[Sentinel] {finding.title}"

    parts = [
        f"**Detector**: {finding.detector}",
        f"**Category**: {finding.category}",
        f"**Severity**: {finding.severity.value}",
        f"**Confidence**: {int(finding.confidence * 100)}%",
        "",
        finding.description,
        "",
    ]

    if finding.file_path:
        location = finding.file_path
        if finding.line_start:
            location += f"#L{finding.line_start}"
            if finding.line_end and finding.line_end != finding.line_start:
                location += f"-L{finding.line_end}"
        parts.append(f"**Location**: `{location}`")
        parts.append("")

    if finding.evidence:
        parts.append("## Evidence")
        parts.append("")
        for ev in finding.evidence:
            parts.append(f"**{ev.type.value}** from `{ev.source}`")
            parts.append("```")
            # Limit evidence to avoid overly long issues
            lines = ev.content.splitlines()
            if len(lines) > 30:
                lines = [*lines[:30], f"... ({len(lines) - 30} more lines)"]
            parts.extend(lines)
            parts.append("```")
            parts.append("")

    # Invisible fingerprint marker for dedup
    parts.append(f"<!-- sentinel:fingerprint:{finding.fingerprint} -->")

    body = "\n".join(parts)
    return title, body


def _issue_labels(finding: Finding) -> list[str]:
    """Generate appropriate GitHub labels for a finding."""
    labels = ["sentinel"]
    labels.append(f"severity:{finding.severity.value}")
    return labels
