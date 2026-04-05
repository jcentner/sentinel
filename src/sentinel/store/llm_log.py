"""Structured LLM interaction logging for analysis and accuracy review."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class LLMLogEntry:
    """A single LLM interaction record."""

    purpose: str  # "judge" or "doc-code-comparison"
    model: str
    prompt: str
    response: str | None = None
    detector: str | None = None
    finding_fingerprint: str | None = None
    finding_title: str | None = None
    tokens_generated: int | None = None
    generation_ms: float | None = None
    verdict: str | None = None  # confirmed, likely_false_positive, accurate, drift_detected, no_parse, error
    is_real: bool | None = None
    adjusted_severity: str | None = None
    summary: str | None = None


def insert_llm_log(
    conn: sqlite3.Connection,
    run_id: int | None,
    entry: LLMLogEntry,
) -> None:
    """Insert a single LLM log entry."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """\
        INSERT INTO llm_log (
            run_id, timestamp, purpose, model, detector,
            finding_fingerprint, finding_title,
            prompt, response, tokens_generated, generation_ms,
            verdict, is_real, adjusted_severity, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            now,
            entry.purpose,
            entry.model,
            entry.detector,
            entry.finding_fingerprint,
            entry.finding_title,
            entry.prompt,
            entry.response,
            entry.tokens_generated,
            entry.generation_ms,
            entry.verdict,
            1 if entry.is_real else (0 if entry.is_real is not None else None),
            entry.adjusted_severity,
            entry.summary,
        ),
    )
    conn.commit()


def get_llm_log_for_run(
    conn: sqlite3.Connection, run_id: int
) -> list[dict[str, Any]]:
    """Retrieve all LLM log entries for a given run."""
    rows = conn.execute(
        "SELECT * FROM llm_log WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def get_llm_log_stats(conn: sqlite3.Connection, run_id: int | None = None) -> dict[str, Any]:
    """Compute summary statistics from the LLM log.

    If run_id is None, computes stats across all runs.
    """
    _STATS_COLUMNS = """\
        COUNT(*) AS total_calls,
        SUM(CASE WHEN purpose = 'judge' THEN 1 ELSE 0 END) AS judge_calls,
        SUM(CASE WHEN purpose = 'doc-code-comparison' THEN 1 ELSE 0 END) AS doc_code_calls,
        SUM(CASE WHEN verdict = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
        SUM(CASE WHEN verdict = 'likely_false_positive' THEN 1 ELSE 0 END) AS likely_fp,
        SUM(CASE WHEN verdict = 'drift_detected' THEN 1 ELSE 0 END) AS drift_detected,
        SUM(CASE WHEN verdict = 'accurate' THEN 1 ELSE 0 END) AS accurate,
        SUM(CASE WHEN verdict = 'error' THEN 1 ELSE 0 END) AS errors,
        SUM(CASE WHEN verdict = 'no_parse' THEN 1 ELSE 0 END) AS no_parse,
        SUM(tokens_generated) AS total_tokens,
        AVG(tokens_generated) AS avg_tokens,
        SUM(generation_ms) AS total_generation_ms,
        AVG(generation_ms) AS avg_generation_ms"""

    if run_id is not None:
        row = conn.execute(
            f"SELECT {_STATS_COLUMNS} FROM llm_log WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    else:
        row = conn.execute(
            f"SELECT {_STATS_COLUMNS} FROM llm_log",
        ).fetchone()

    return dict(row) if row else {}
