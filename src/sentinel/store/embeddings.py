"""Embedding chunk storage — CRUD for the chunks table."""

from __future__ import annotations

import hashlib
import logging
import math
import sqlite3
import struct
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def content_hash(text: str) -> str:
    """SHA256 hex digest of text content (for change detection)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _pack_embedding(vec: list[float]) -> bytes:
    """Pack a float list into raw float32 bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_embedding(blob: bytes) -> list[float]:
    """Unpack raw float32 bytes back to a float list."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors. Pure Python."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# --- Write operations ---


def upsert_chunks(
    conn: sqlite3.Connection,
    file_path: str,
    chunks: list[dict],
    embed_model: str,
) -> int:
    """Insert or replace chunks for a given file.

    Each chunk dict has keys: start_line, end_line, content, embedding.
    Returns the number of chunks written.
    """
    now = datetime.now(UTC).isoformat()
    # Delete old chunks for this file first (simpler than per-chunk upsert)
    conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))

    for chunk in chunks:
        conn.execute(
            """INSERT INTO chunks
               (file_path, start_line, end_line, content_hash, content, embedding, embed_model, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_path,
                chunk["start_line"],
                chunk["end_line"],
                content_hash(chunk["content"]),
                chunk["content"],
                _pack_embedding(chunk["embedding"]),
                embed_model,
                now,
            ),
        )
    conn.commit()
    return len(chunks)


def delete_file_chunks(conn: sqlite3.Connection, file_path: str) -> int:
    """Delete all chunks for a given file. Returns rows deleted."""
    cursor = conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
    conn.commit()
    return cursor.rowcount


def clear_all_chunks(conn: sqlite3.Connection) -> int:
    """Delete all chunks. Returns rows deleted."""
    cursor = conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM embed_meta")
    conn.commit()
    return cursor.rowcount


# --- Read operations ---


def get_file_content_hashes(
    conn: sqlite3.Connection,
) -> dict[str, set[str]]:
    """Return {file_path: {content_hash, ...}} for all indexed files."""
    rows = conn.execute(
        "SELECT file_path, content_hash FROM chunks"
    ).fetchall()
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(row["file_path"], set()).add(row["content_hash"])
    return result


def get_indexed_files(conn: sqlite3.Connection) -> set[str]:
    """Return the set of file paths that have at least one chunk."""
    rows = conn.execute("SELECT DISTINCT file_path FROM chunks").fetchall()
    return {row["file_path"] for row in rows}


def chunk_count(conn: sqlite3.Connection) -> int:
    """Return the total number of stored chunks."""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM chunks").fetchone()
    return row["cnt"]


def query_similar(
    conn: sqlite3.Connection,
    query_vec: list[float],
    top_k: int = 5,
    exclude_file: str | None = None,
) -> list[dict]:
    """Find the top-k most similar chunks to a query vector.

    Returns a list of dicts with keys: file_path, start_line, end_line,
    content, similarity.
    """
    total = chunk_count(conn)
    if total > 50_000:
        logger.warning(
            "Embedding index has %d chunks — consider switching to sqlite-vec "
            "for better query performance (see ADR-009)",
            total,
        )

    if exclude_file:
        rows = conn.execute(
            "SELECT file_path, start_line, end_line, content, embedding "
            "FROM chunks WHERE file_path != ?",
            (exclude_file,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT file_path, start_line, end_line, content, embedding FROM chunks"
        ).fetchall()

    scored = []
    for row in rows:
        vec = _unpack_embedding(row["embedding"])
        sim = cosine_similarity(query_vec, vec)
        scored.append(
            {
                "file_path": row["file_path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "content": row["content"],
                "similarity": sim,
            }
        )

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]


# --- Metadata ---


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Set a metadata key-value pair."""
    conn.execute(
        "INSERT OR REPLACE INTO embed_meta (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Get a metadata value by key."""
    row = conn.execute(
        "SELECT value FROM embed_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None
