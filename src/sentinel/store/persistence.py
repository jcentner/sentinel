"""Finding persistence tracking — occurrence counts and temporal history."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class PersistenceInfo:
    """Persistence metadata for a finding fingerprint."""

    fingerprint: str
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int


def update_persistence(
    conn: sqlite3.Connection, fingerprints: list[str]
) -> dict[str, PersistenceInfo]:
    """Update persistence records for a batch of fingerprints.

    Returns a dict mapping fingerprint → PersistenceInfo (after update).
    """
    now = datetime.now(UTC).isoformat()
    result: dict[str, PersistenceInfo] = {}

    for fp in fingerprints:
        conn.execute(
            """
            INSERT INTO finding_persistence (fingerprint, first_seen, last_seen, occurrence_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(fingerprint) DO UPDATE SET
                last_seen = excluded.last_seen,
                occurrence_count = occurrence_count + 1
            """,
            (fp, now, now),
        )

    conn.commit()

    # Fetch updated records
    if fingerprints:
        placeholders = ",".join("?" for _ in fingerprints)
        rows = conn.execute(
            f"SELECT * FROM finding_persistence WHERE fingerprint IN ({placeholders})",
            fingerprints,
        ).fetchall()
        for row in rows:
            result[row["fingerprint"]] = PersistenceInfo(
                fingerprint=row["fingerprint"],
                first_seen=datetime.fromisoformat(row["first_seen"]),
                last_seen=datetime.fromisoformat(row["last_seen"]),
                occurrence_count=row["occurrence_count"],
            )

    return result


def get_persistence_info(
    conn: sqlite3.Connection, fingerprints: list[str]
) -> dict[str, PersistenceInfo]:
    """Look up persistence info for a set of fingerprints (read-only)."""
    if not fingerprints:
        return {}

    placeholders = ",".join("?" for _ in fingerprints)
    rows = conn.execute(
        f"SELECT * FROM finding_persistence WHERE fingerprint IN ({placeholders})",
        fingerprints,
    ).fetchall()

    return {
        row["fingerprint"]: PersistenceInfo(
            fingerprint=row["fingerprint"],
            first_seen=datetime.fromisoformat(row["first_seen"]),
            last_seen=datetime.fromisoformat(row["last_seen"]),
            occurrence_count=row["occurrence_count"],
        )
        for row in rows
    }
