"""CRUD operations for findings and suppressions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from sentinel.models import (
    Evidence,
    Finding,
    FindingStatus,
    Severity,
)


def insert_finding(conn: sqlite3.Connection, run_id: int, finding: Finding) -> int:
    """Insert a finding and return its database ID."""
    cur = conn.execute(
        """
        INSERT INTO findings
            (run_id, fingerprint, detector, category, severity, confidence,
             title, description, file_path, line_start, line_end,
             evidence_json, context_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            finding.fingerprint,
            finding.detector,
            finding.category,
            finding.severity.value,
            finding.confidence,
            finding.title,
            finding.description,
            finding.file_path,
            finding.line_start,
            finding.line_end,
            finding.evidence_json(),
            finding.context_json(),
            finding.status.value,
            finding.timestamp.isoformat(),
        ),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_findings_by_run(conn: sqlite3.Connection, run_id: int) -> list[Finding]:
    """Retrieve all findings for a given run."""
    rows = conn.execute(
        "SELECT * FROM findings WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()
    return [_row_to_finding(row) for row in rows]


def get_finding_by_id(conn: sqlite3.Connection, finding_id: int) -> Finding | None:
    """Retrieve a single finding by its database ID."""
    row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
    if row is None:
        return None
    return _row_to_finding(row)


def get_suppressed_fingerprints(conn: sqlite3.Connection) -> set[str]:
    """Return all suppressed fingerprints."""
    rows = conn.execute("SELECT fingerprint FROM suppressions").fetchall()
    return {row["fingerprint"] for row in rows}


def suppress_finding(
    conn: sqlite3.Connection, fingerprint: str, reason: str | None = None
) -> None:
    """Add a fingerprint to the suppression list."""
    from datetime import datetime

    conn.execute(
        """
        INSERT OR IGNORE INTO suppressions (fingerprint, reason, suppressed_at)
        VALUES (?, ?, ?)
        """,
        (fingerprint, reason, datetime.now(UTC).isoformat()),
    )
    # Also update status on any existing findings with this fingerprint
    conn.execute(
        "UPDATE findings SET status = ? WHERE fingerprint = ?",
        (FindingStatus.SUPPRESSED.value, fingerprint),
    )
    conn.commit()


def update_finding_status(
    conn: sqlite3.Connection, finding_id: int, status: FindingStatus
) -> None:
    """Update the status of a finding."""
    conn.execute(
        "UPDATE findings SET status = ? WHERE id = ?", (status.value, finding_id)
    )
    conn.commit()


def compare_runs(
    conn: sqlite3.Connection,
    base_run_id: int,
    target_run_id: int,
) -> tuple[list[Finding], list[Finding], list[Finding]]:
    """Compare findings between two runs using fingerprints.

    Returns (new_findings, resolved_findings, persistent_findings):
    - new: in target but not in base
    - resolved: in base but not in target
    - persistent: in both runs
    """
    base = get_findings_by_run(conn, base_run_id)
    target = get_findings_by_run(conn, target_run_id)

    base_fps = {f.fingerprint: f for f in base}
    target_fps = {f.fingerprint: f for f in target}

    new = [f for fp, f in target_fps.items() if fp not in base_fps]
    resolved = [f for fp, f in base_fps.items() if fp not in target_fps]
    persistent = [f for fp, f in target_fps.items() if fp in base_fps]

    return new, resolved, persistent


def get_known_fingerprints(
    conn: sqlite3.Connection,
    retention_days: int = 90,
) -> set[str]:
    """Return fingerprints seen within the retention window (for dedup).

    Args:
        conn: Database connection.
        retention_days: Only consider findings from the last N days.
            Use 0 to disable the window (return all fingerprints).
    """
    if retention_days > 0:
        rows = conn.execute(
            "SELECT DISTINCT fingerprint FROM findings "
            "WHERE created_at >= datetime('now', ?)",
            (f"-{retention_days} days",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT DISTINCT fingerprint FROM findings").fetchall()
    return {row["fingerprint"] for row in rows}


def _row_to_finding(row: sqlite3.Row) -> Finding:
    """Convert a database row to a Finding object."""
    import json
    from datetime import datetime

    evidence_data = json.loads(row["evidence_json"])
    evidence = [Evidence.from_dict(e) for e in evidence_data]

    context = None
    if row["context_json"]:
        context = json.loads(row["context_json"])

    timestamp = datetime.fromisoformat(row["created_at"])

    return Finding(
        detector=row["detector"],
        category=row["category"],
        severity=Severity(row["severity"]),
        confidence=row["confidence"],
        title=row["title"],
        description=row["description"],
        evidence=evidence,
        file_path=row["file_path"],
        line_start=row["line_start"],
        line_end=row["line_end"],
        context=context,
        fingerprint=row["fingerprint"],
        status=FindingStatus(row["status"]),
        timestamp=timestamp,
        id=row["id"],
    )


# -------------------------------------------------------------------
# Annotations
# -------------------------------------------------------------------


@dataclass
class Annotation:
    """A user note attached to a finding."""

    id: int
    finding_id: int
    content: str
    created_at: datetime


def add_annotation(
    conn: sqlite3.Connection, finding_id: int, content: str
) -> int:
    """Add an annotation to a finding. Returns the annotation ID."""
    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        "INSERT INTO annotations (finding_id, content, created_at) VALUES (?, ?, ?)",
        (finding_id, content, now),
    )
    conn.commit()
    return cur.lastrowid or 0


def get_annotations(
    conn: sqlite3.Connection, finding_id: int
) -> list[Annotation]:
    """Get all annotations for a finding, ordered by creation time."""
    rows = conn.execute(
        "SELECT id, finding_id, content, created_at FROM annotations "
        "WHERE finding_id = ? ORDER BY created_at ASC",
        (finding_id,),
    ).fetchall()
    return [
        Annotation(
            id=row["id"],
            finding_id=row["finding_id"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


def delete_annotation(
    conn: sqlite3.Connection, annotation_id: int, finding_id: int | None = None
) -> bool:
    """Delete an annotation by ID. If finding_id is given, also verifies ownership."""
    if finding_id is not None:
        cur = conn.execute(
            "DELETE FROM annotations WHERE id = ? AND finding_id = ?",
            (annotation_id, finding_id),
        )
    else:
        cur = conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
    conn.commit()
    return cur.rowcount > 0


# -------------------------------------------------------------------
# Data lifecycle (TD-020)
# -------------------------------------------------------------------


def prune_old_data(
    conn: sqlite3.Connection,
    retention_days: int = 90,
) -> dict[str, int]:
    """Delete data older than retention_days. Returns counts of deleted rows.

    Deletes:
    - llm_log entries older than retention_days
    - findings (and their annotations) for runs older than retention_days
    - runs older than retention_days
    - finding_persistence entries not seen within retention_days

    Does NOT delete suppressions (they are user decisions, not ephemeral data).
    """
    cutoff = f"-{retention_days} days"
    deleted: dict[str, int] = {}

    # 1. Delete old llm_log entries
    cur = conn.execute(
        "DELETE FROM llm_log WHERE timestamp < datetime('now', ?)", (cutoff,)
    )
    deleted["llm_log"] = cur.rowcount

    # 2. Find old run IDs
    old_runs = conn.execute(
        "SELECT id FROM runs WHERE started_at < datetime('now', ?)", (cutoff,)
    ).fetchall()
    old_run_ids = [r["id"] for r in old_runs]

    if old_run_ids:
        placeholders = ",".join("?" * len(old_run_ids))

        # 3. Delete annotations for findings in old runs
        cur = conn.execute(
            f"DELETE FROM annotations WHERE finding_id IN "
            f"(SELECT id FROM findings WHERE run_id IN ({placeholders}))",
            old_run_ids,
        )
        deleted["annotations"] = cur.rowcount

        # 4. Delete findings in old runs
        cur = conn.execute(
            f"DELETE FROM findings WHERE run_id IN ({placeholders})",
            old_run_ids,
        )
        deleted["findings"] = cur.rowcount

        # 5. Delete old runs
        cur = conn.execute(
            f"DELETE FROM runs WHERE id IN ({placeholders})",
            old_run_ids,
        )
        deleted["runs"] = cur.rowcount
    else:
        deleted["annotations"] = 0
        deleted["findings"] = 0
        deleted["runs"] = 0

    # 6. Prune stale persistence entries
    cur = conn.execute(
        "DELETE FROM finding_persistence WHERE last_seen < datetime('now', ?)",
        (cutoff,),
    )
    deleted["finding_persistence"] = cur.rowcount

    conn.commit()

    # 7. Vacuum to reclaim space
    conn.execute("VACUUM")

    return deleted
