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


def get_known_fingerprints(conn: sqlite3.Connection) -> set[str]:
    """Return all fingerprints ever seen (for dedup)."""
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
    conn: sqlite3.Connection, annotation_id: int
) -> bool:
    """Delete an annotation by ID. Returns True if deleted."""
    cur = conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
    conn.commit()
    return cur.rowcount > 0
