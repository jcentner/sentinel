"""Run history tracking."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from sentinel.models import RunSummary, ScopeType


def create_run(
    conn: sqlite3.Connection, repo_path: str, scope: ScopeType = ScopeType.FULL
) -> RunSummary:
    """Create a new run record and return a RunSummary."""
    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO runs (repo_path, started_at, scope) VALUES (?, ?, ?)",
        (repo_path, now.isoformat(), scope.value),
    )
    conn.commit()
    return RunSummary(
        id=cur.lastrowid,
        repo_path=repo_path,
        started_at=now,
        scope=scope,
    )


def complete_run(
    conn: sqlite3.Connection, run_id: int, finding_count: int
) -> None:
    """Mark a run as completed."""
    now = datetime.now(timezone.utc)
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


def _row_to_run(row: sqlite3.Row) -> RunSummary:
    """Convert a database row to a RunSummary."""
    completed = None
    if row["completed_at"]:
        completed = datetime.fromisoformat(row["completed_at"])

    return RunSummary(
        id=row["id"],
        repo_path=row["repo_path"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=completed,
        scope=ScopeType(row["scope"]),
        finding_count=row["finding_count"],
    )
