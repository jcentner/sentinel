"""SQLite database connection, schema creation, and migrations."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Bump this when adding new migrations. Must equal the highest migration version.
SCHEMA_VERSION = 7

# -------------------------------------------------------------------
# Base schema (v1) — applied to fresh databases
# -------------------------------------------------------------------
_SCHEMA_V1_SQL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    scope TEXT NOT NULL DEFAULT 'full',
    finding_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    fingerprint TEXT NOT NULL,
    detector TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    file_path TEXT,
    line_start INTEGER,
    line_end INTEGER,
    evidence_json TEXT NOT NULL,
    context_json TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suppressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    reason TEXT,
    suppressed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_fingerprint ON findings(fingerprint);
CREATE INDEX IF NOT EXISTS idx_findings_run_id ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_suppressions_fingerprint ON suppressions(fingerprint);
"""

# -------------------------------------------------------------------
# Migrations — applied sequentially after the base schema
# Each entry: (version, description, SQL string)
# -------------------------------------------------------------------
_MIGRATIONS: list[tuple[int, str, str]] = [
    (
        2,
        "add finding_persistence table",
        """\
CREATE TABLE IF NOT EXISTS finding_persistence (
    fingerprint TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1
);
""",
    ),
    (
        3,
        "add llm_log table for structured LLM interaction logging",
        """\
CREATE TABLE IF NOT EXISTS llm_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES runs(id),
    timestamp TEXT NOT NULL,
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    detector TEXT,
    finding_fingerprint TEXT,
    finding_title TEXT,
    prompt TEXT NOT NULL,
    response TEXT,
    tokens_generated INTEGER,
    generation_ms REAL,
    verdict TEXT,
    is_real INTEGER,
    adjusted_severity TEXT,
    summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_log_run_id ON llm_log(run_id);
CREATE INDEX IF NOT EXISTS idx_llm_log_purpose ON llm_log(purpose);
CREATE INDEX IF NOT EXISTS idx_llm_log_verdict ON llm_log(verdict);
CREATE INDEX IF NOT EXISTS idx_llm_log_finding_fingerprint ON llm_log(finding_fingerprint);
""",
    ),
    (
        4,
        "add commit_sha column to runs table",
        "ALTER TABLE runs ADD COLUMN commit_sha TEXT;",
    ),
    (
        5,
        "add embedding chunks table for semantic context",
        """\
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,
    embed_model TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks(content_hash);

CREATE TABLE IF NOT EXISTS embed_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
""",
    ),
    (
        6,
        "add eval_results table for persistent evaluation metrics",
        """\
CREATE TABLE IF NOT EXISTS eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    total_findings INTEGER NOT NULL,
    true_positives INTEGER NOT NULL,
    false_positives_found INTEGER NOT NULL,
    missing_count INTEGER NOT NULL,
    precision REAL NOT NULL,
    recall REAL NOT NULL,
    ground_truth_path TEXT,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_eval_results_repo ON eval_results(repo_path);
CREATE INDEX IF NOT EXISTS idx_eval_results_date ON eval_results(evaluated_at);
""",
    ),
    (
        7,
        "add annotations table for user notes on findings",
        """\
CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES findings(id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_annotations_finding_id ON annotations(finding_id);
""",
    ),
]


def get_connection(
    db_path: str | Path, *, check_same_thread: bool = True
) -> sqlite3.Connection:
    """Open (or create) a SQLite database and ensure schema is current."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist and apply pending migrations."""
    conn.executescript(_SCHEMA_V1_SQL)

    row = conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()

    current_version = row["version"] if row else 0

    if current_version == 0:
        # Fresh database — stamp it at v1
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (1,))
        conn.commit()
        current_version = 1

    # Apply any pending migrations
    _apply_migrations(conn, current_version)


def _apply_migrations(conn: sqlite3.Connection, current_version: int) -> None:
    """Apply all migrations newer than current_version."""
    for version, description, sql in _MIGRATIONS:
        if version > current_version:
            logger.info("Applying migration v%d: %s", version, description)
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            conn.commit()
            logger.info("Migration v%d applied successfully", version)
