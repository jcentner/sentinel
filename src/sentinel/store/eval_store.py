"""Store layer for persistent evaluation results."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class StoredEvalResult:
    """A persisted evaluation result."""

    id: int | None
    repo_path: str
    evaluated_at: datetime
    total_findings: int
    true_positives: int
    false_positives_found: int
    missing_count: int
    precision: float
    recall: float
    ground_truth_path: str | None
    details: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repo_path": self.repo_path,
            "evaluated_at": self.evaluated_at.isoformat(),
            "total_findings": self.total_findings,
            "true_positives": self.true_positives,
            "false_positives_found": self.false_positives_found,
            "missing_count": self.missing_count,
            "precision": self.precision,
            "recall": self.recall,
            "ground_truth_path": self.ground_truth_path,
            "details": self.details,
        }


def save_eval_result(
    conn: sqlite3.Connection,
    repo_path: str,
    total_findings: int,
    true_positives: int,
    false_positives_found: int,
    missing_count: int,
    precision: float,
    recall: float,
    ground_truth_path: str | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    """Save an evaluation result and return its ID."""
    now = datetime.now(UTC).isoformat()
    details_json = json.dumps(details) if details else None
    cursor = conn.execute(
        """INSERT INTO eval_results
           (repo_path, evaluated_at, total_findings, true_positives,
            false_positives_found, missing_count, precision, recall,
            ground_truth_path, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (repo_path, now, total_findings, true_positives,
         false_positives_found, missing_count, precision, recall,
         ground_truth_path, details_json),
    )
    conn.commit()
    return cursor.lastrowid or 0


def get_eval_history(
    conn: sqlite3.Connection,
    repo_path: str | None = None,
    limit: int = 50,
) -> list[StoredEvalResult]:
    """Get eval results, optionally filtered by repo. Most recent first."""
    if repo_path:
        rows = conn.execute(
            """SELECT * FROM eval_results
               WHERE repo_path = ?
               ORDER BY evaluated_at DESC LIMIT ?""",
            (repo_path, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM eval_results
               ORDER BY evaluated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    return [_row_to_result(r) for r in rows]


def _row_to_result(row: sqlite3.Row) -> StoredEvalResult:
    """Convert a DB row to a StoredEvalResult."""
    details_raw = row["details_json"]
    details = json.loads(details_raw) if details_raw else None
    return StoredEvalResult(
        id=row["id"],
        repo_path=row["repo_path"],
        evaluated_at=datetime.fromisoformat(row["evaluated_at"]),
        total_findings=row["total_findings"],
        true_positives=row["true_positives"],
        false_positives_found=row["false_positives_found"],
        missing_count=row["missing_count"],
        precision=row["precision"],
        recall=row["recall"],
        ground_truth_path=row["ground_truth_path"],
        details=details,
    )
