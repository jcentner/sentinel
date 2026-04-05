"""Context gatherer — enriches findings with surrounding code, related files,
git history, and (optionally) embedding-based semantic context.
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
from pathlib import Path

from sentinel.models import Evidence, EvidenceType, Finding

logger = logging.getLogger(__name__)

# How many lines of context to gather around a finding
_CONTEXT_LINES = 5

# Max git log entries per file
_GIT_LOG_LIMIT = 5

# Number of similar chunks to include when embeddings are available
_EMBED_TOP_K = 5


def gather_context(
    findings: list[Finding],
    repo_root: str,
    conn: sqlite3.Connection | None = None,
    embed_model: str = "",
    ollama_url: str = "http://localhost:11434",
) -> list[Finding]:
    """Enrich each finding with surrounding context from the repo.

    If conn and embed_model are provided and an embedding index exists,
    also adds semantically similar chunks as evidence. Falls back to
    file-proximity heuristics only when embeddings are unavailable.
    """
    root = Path(repo_root)
    use_embeddings = bool(conn and embed_model)

    if use_embeddings:
        try:
            from sentinel.store.embeddings import chunk_count
            if chunk_count(conn) == 0:
                logger.info("Embedding index is empty, using heuristic context only")
                use_embeddings = False
        except Exception:
            use_embeddings = False

    for f in findings:
        if f.file_path and f.line_start:
            _add_surrounding_code(f, root)
        if f.file_path:
            _add_related_files(f, root)
            _add_git_log(f, root)
        if use_embeddings:
            _add_embedding_context(f, conn, embed_model, ollama_url)
    return findings


def _add_surrounding_code(finding: Finding, root: Path) -> None:
    """Add lines surrounding the finding location."""
    file_path = root / finding.file_path
    if not file_path.is_file():
        return

    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return

    start = max(0, finding.line_start - 1 - _CONTEXT_LINES)
    end = min(len(lines), finding.line_start + _CONTEXT_LINES)
    snippet = "\n".join(
        f"{i + 1:4d} | {lines[i]}" for i in range(start, end)
    )

    if snippet:
        finding.evidence.append(
            Evidence(
                type=EvidenceType.CODE,
                source=finding.file_path,
                content=snippet,
                line_range=(start + 1, end),
            )
        )


def _add_related_files(finding: Finding, root: Path) -> None:
    """Look for test or doc files related to the finding's file."""
    if not finding.file_path:
        return

    src_path = Path(finding.file_path)
    stem = src_path.stem
    parent = src_path.parent

    # Common test file patterns
    test_candidates = [
        parent / f"test_{stem}.py",
        parent.parent / "tests" / f"test_{stem}.py",
        Path("tests") / f"test_{stem}.py",
        Path("tests") / parent.name / f"test_{stem}.py",
    ]

    for candidate in test_candidates:
        full = root / candidate
        if full.is_file():
            try:
                content = full.read_text(encoding="utf-8", errors="ignore")
                # Only include first 30 lines to keep context manageable
                preview = "\n".join(content.splitlines()[:30])
                finding.evidence.append(
                    Evidence(
                        type=EvidenceType.TEST,
                        source=str(candidate),
                        content=preview,
                    )
                )
            except OSError:
                pass
            break  # Only add one related test file


def _add_git_log(finding: Finding, root: Path) -> None:
    """Add recent git log entries for the finding's file."""
    if not finding.file_path:
        return

    try:
        result = subprocess.run(
            [
                "git", "log", f"-{_GIT_LOG_LIMIT}",
                "--oneline", "--", finding.file_path,
            ],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            finding.evidence.append(
                Evidence(
                    type=EvidenceType.GIT_HISTORY,
                    source=finding.file_path,
                    content=result.stdout.strip(),
                )
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _add_embedding_context(
    finding: Finding,
    conn: sqlite3.Connection,
    embed_model: str,
    ollama_url: str,
) -> None:
    """Add semantically similar code chunks as evidence via embeddings."""
    from sentinel.core.ollama import embed_texts
    from sentinel.store.embeddings import query_similar

    # Build a query from the finding's title and description
    query_text = f"{finding.title}\n{finding.description}"
    vectors = embed_texts([query_text], embed_model, ollama_url)
    if not vectors or not vectors[0]:
        return

    query_vec = vectors[0]
    results = query_similar(
        conn,
        query_vec,
        top_k=_EMBED_TOP_K,
        exclude_file=finding.file_path,
    )

    for r in results:
        if r["similarity"] < 0.3:
            break  # Below threshold — remaining results are even less relevant
        # Truncate content to keep context manageable
        content_lines = r["content"].splitlines()
        if len(content_lines) > 30:
            content_lines = content_lines[:30]
            content_lines.append("... (truncated)")
        finding.evidence.append(
            Evidence(
                type=EvidenceType.CODE,
                source=f"{r['file_path']}:{r['start_line']}-{r['end_line']}",
                content="\n".join(content_lines),
                line_range=(r["start_line"], r["end_line"]),
            )
        )
