"""Embedding index builder — chunk repo files, embed via Ollama, store in SQLite."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from pathlib import Path

from sentinel.core.ollama import embed_texts
from sentinel.store.embeddings import (
    delete_file_chunks,
    get_indexed_files,
    set_meta,
    upsert_chunks,
)

logger = logging.getLogger(__name__)

# Directories always skipped during indexing
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".sentinel", ".eggs",
}

# Binary / non-text extensions to skip
_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".o", ".a",
    ".tar", ".gz", ".zip", ".bz2", ".xz", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".db", ".sqlite", ".sqlite3",
    ".lock", ".sum",
}

# Max file size to index (skip very large files)
_MAX_FILE_SIZE = 500_000  # ~500 KB


def _should_skip_dir(name: str) -> bool:
    """Check if a directory name should be skipped."""
    return name in _SKIP_DIRS or name.endswith(".egg-info")


def _should_skip_file(path: Path) -> bool:
    """Check if a file should be skipped based on extension/size."""
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return True
    try:
        size = path.stat().st_size
        if size > _MAX_FILE_SIZE or size == 0:
            return True
    except OSError:
        return True
    return False


def _collect_files(repo_root: Path) -> list[Path]:
    """Recursively collect indexable files from repo."""
    files: list[Path] = []
    for item in sorted(repo_root.iterdir()):
        if item.is_dir():
            if not _should_skip_dir(item.name):
                files.extend(_collect_files(item))
        elif item.is_file() and not _should_skip_file(item):
            files.append(item)
    return files


def _file_content_hash(path: Path) -> str:
    """SHA256 hash of entire file content (for change detection)."""
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()[:16]


def chunk_file(
    content: str,
    chunk_size: int = 50,
    chunk_overlap: int = 10,
) -> list[dict]:
    """Split file content into overlapping line-based chunks.

    Returns list of dicts with start_line (1-based), end_line, content.
    """
    lines = content.splitlines(keepends=True)
    if not lines:
        return []

    chunks = []
    step = max(1, chunk_size - chunk_overlap)
    i = 0
    while i < len(lines):
        end = min(i + chunk_size, len(lines))
        chunk_text = "".join(lines[i:end])
        if chunk_text.strip():  # skip empty chunks
            chunks.append({
                "start_line": i + 1,
                "end_line": end,
                "content": chunk_text,
            })
        if end >= len(lines):
            break
        i += step

    return chunks


def build_index(
    repo_root: str,
    conn: sqlite3.Connection,
    embed_model: str,
    ollama_url: str = "http://localhost:11434",
    chunk_size: int = 50,
    chunk_overlap: int = 10,
    batch_size: int = 20,
) -> dict:
    """Build or update the embedding index for a repository.

    Returns a summary dict with counts: files_scanned, files_indexed,
    files_skipped, chunks_created, files_removed.
    """
    root = Path(repo_root)
    stats = {
        "files_scanned": 0,
        "files_indexed": 0,
        "files_skipped": 0,
        "chunks_created": 0,
        "files_removed": 0,
    }

    # Collect all indexable files
    all_files = _collect_files(root)
    stats["files_scanned"] = len(all_files)

    # Build {rel_path: file_hash} for current repo state
    current_files: dict[str, tuple[Path, str]] = {}
    for f in all_files:
        rel = str(f.relative_to(root))
        fhash = _file_content_hash(f)
        current_files[rel] = (f, fhash)

    # Get existing indexed files
    indexed_files = get_indexed_files(conn)

    # Remove chunks for files that no longer exist
    for old_path in indexed_files - set(current_files.keys()):
        delete_file_chunks(conn, old_path)
        stats["files_removed"] += 1

    # Check which files need (re-)indexing by comparing stored content hashes
    # We use the embed_meta table to store per-file hashes
    files_to_index: list[tuple[str, Path]] = []
    for rel_path, (abs_path, fhash) in current_files.items():
        stored_hash = _get_file_hash(conn, rel_path)
        if stored_hash != fhash:
            files_to_index.append((rel_path, abs_path))

    if not files_to_index:
        logger.info("Embedding index is up-to-date, no files changed")
        return stats

    logger.info("Indexing %d files for embeddings", len(files_to_index))

    # Process files in batches to limit memory and API calls
    for rel_path, abs_path in files_to_index:
        try:
            text = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            logger.warning("Could not read %s, skipping", rel_path)
            stats["files_skipped"] += 1
            continue

        chunks = chunk_file(text, chunk_size, chunk_overlap)
        if not chunks:
            stats["files_skipped"] += 1
            continue

        # Embed chunks in batches
        all_embedded_chunks = []
        for batch_start in range(0, len(chunks), batch_size):
            batch = chunks[batch_start : batch_start + batch_size]
            texts = [c["content"] for c in batch]
            vectors = embed_texts(texts, embed_model, ollama_url)

            if vectors is None:
                logger.warning(
                    "Embedding failed for %s (batch %d), skipping file",
                    rel_path, batch_start // batch_size,
                )
                stats["files_skipped"] += 1
                break
            if len(vectors) != len(batch):
                logger.warning(
                    "Embedding count mismatch for %s: expected %d, got %d",
                    rel_path, len(batch), len(vectors),
                )
                stats["files_skipped"] += 1
                break

            for chunk, vec in zip(batch, vectors, strict=True):
                chunk["embedding"] = vec
                all_embedded_chunks.append(chunk)
        else:
            # All batches succeeded — store chunks
            n = upsert_chunks(conn, rel_path, all_embedded_chunks, embed_model)
            fhash = current_files[rel_path][1]
            _set_file_hash(conn, rel_path, fhash)
            stats["files_indexed"] += 1
            stats["chunks_created"] += n
            logger.debug("Indexed %s: %d chunks", rel_path, n)

    set_meta(conn, "embed_model", embed_model)
    logger.info(
        "Indexing complete: %d files indexed, %d chunks created",
        stats["files_indexed"], stats["chunks_created"],
    )
    return stats


def _get_file_hash(conn: sqlite3.Connection, file_path: str) -> str | None:
    """Get stored content hash for a file."""
    row = conn.execute(
        "SELECT value FROM embed_meta WHERE key = ?",
        (f"file_hash:{file_path}",),
    ).fetchone()
    return row["value"] if row else None


def _set_file_hash(conn: sqlite3.Connection, file_path: str, fhash: str) -> None:
    """Store content hash for a file."""
    conn.execute(
        "INSERT OR REPLACE INTO embed_meta (key, value) VALUES (?, ?)",
        (f"file_hash:{file_path}", fhash),
    )
    conn.commit()
