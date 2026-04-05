"""Run history tracking."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from sentinel.models import RunSummary, ScopeType


def create_run(
    conn: sqlite3.Connection,
    repo_path: str,
    scope: ScopeType = ScopeType.FULL,
    commit_sha: str | None = None,
) -> RunSummary:
    """Create a new run record and return a RunSummary."""
    now = datetime.now(UTC)
    cur = conn.execute(
        "INSERT INTO runs (repo_path, started_at, scope, commit_sha) VALUES (?, ?, ?, ?)",
        (repo_path, now.isoformat(), scope.value, commit_sha),
    )
    conn.commit()
    return RunSummary(
        id=cur.lastrowid,
        repo_path=repo_path,
        started_at=now,
        scope=scope,
        commit_sha=commit_sha,
    )


def complete_run(
    conn: sqlite3.Connection, run_id: int, finding_count: int
) -> None:
    """Mark a run as completed."""
    now = datetime.now(UTC)
    conn.execute(
        "UPDATE runs SET completed_at = ?, finding_count = ? WHERE id = ?",
        (now.isoformat(), finding_count, run_id),
    )
    conn.commit()


def get_run_history(
    conn: sqlite3.Connection, repo_path: str | None = None, limit: int = 20
) -> list[RunSummary]:
    """Retrieve recent run summaries, optionally filtered by repo."""
    if repo_path:
        rows = conn.execute(
            "SELECT * FROM runs WHERE repo_path = ? ORDER BY id DESC LIMIT ?",
            (repo_path, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_run(row) for row in rows]


def get_run_by_id(conn: sqlite3.Connection, run_id: int) -> RunSummary | None:
    """Retrieve a single run by ID."""
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return _row_to_run(row)


def get_last_completed_run(
    conn: sqlite3.Connection, repo_path: str
) -> RunSummary | None:
    """Return the most recent completed run for a repo, or None."""
    row = conn.execute(
        "SELECT * FROM runs WHERE repo_path = ? AND completed_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 1",
        (repo_path,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_run(row)


def _row_to_run(row: sqlite3.Row) -> RunSummary:
    """Convert a database row to a RunSummary."""
    completed = None
    if row["completed_at"]:
        completed = datetime.fromisoformat(row["completed_at"])

    # commit_sha may not exist in older databases without migration v4
    try:
        commit_sha = row["commit_sha"]
    except (IndexError, KeyError):
        commit_sha = None

    return RunSummary(
        id=row["id"],
        repo_path=row["repo_path"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=completed,
        scope=ScopeType(row["scope"]),
        finding_count=row["finding_count"],
        commit_sha=commit_sha,
    )
