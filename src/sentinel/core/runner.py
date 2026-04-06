"""Pipeline runner — orchestrates the full scan pipeline."""

from __future__ import annotations

import logging
import sqlite3
import subprocess
from pathlib import Path

from sentinel.core.context import gather_context
from sentinel.core.dedup import assign_fingerprints, deduplicate
from sentinel.core.judge import judge_findings
from sentinel.core.report import generate_report
from sentinel.detectors.base import Detector, get_all_detectors
from sentinel.models import DetectorContext, Finding, RunSummary, ScopeType
from sentinel.store.findings import insert_finding
from sentinel.store.persistence import update_persistence
from sentinel.store.runs import complete_run, create_run, get_last_completed_run

logger = logging.getLogger(__name__)


def git_head_sha(repo_root: str) -> str | None:
    """Return the HEAD commit SHA for the repo, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=repo_root, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def git_changed_files(repo_root: str, since_sha: str) -> list[str] | None:
    """Return files changed between *since_sha* and HEAD (relative paths).

    Returns None if the git diff command fails (e.g. since_sha was
    force-pushed away), as distinct from an empty list meaning no
    files changed.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", since_sha, "HEAD"],
            capture_output=True, text=True, cwd=repo_root, timeout=30,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().splitlines() if f]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def run_scan(
    repo_path: str,
    conn: sqlite3.Connection,
    *,
    scope: ScopeType = ScopeType.FULL,
    changed_files: list[str] | None = None,
    target_paths: list[str] | None = None,
    detectors: list[Detector] | None = None,
    model: str = "qwen3.5:4b",
    ollama_url: str = "http://localhost:11434",
    output_path: str | None = None,
    skip_judge: bool = False,
    embed_model: str = "",
    embed_chunk_size: int = 50,
    embed_chunk_overlap: int = 10,
    detectors_dir: str = "",
) -> tuple[RunSummary, list[Finding], str]:
    """Execute the full scan pipeline.

    Returns (run_summary, findings, report_text).
    """
    repo_root = str(Path(repo_path).resolve())
    commit_sha = git_head_sha(repo_root)

    # 1. Create run record
    run = create_run(conn, repo_root, scope, commit_sha=commit_sha)
    logger.info("Started run #%d on %s (scope: %s)", run.id, repo_root, scope.value)

    # 2. Build detector context
    ctx = DetectorContext(
        repo_root=repo_root,
        scope=scope,
        changed_files=changed_files,
        target_paths=target_paths,
        config={
            "ollama_url": ollama_url,
            "model": model,
            "skip_llm": skip_judge,
        },
        conn=conn,
        run_id=run.id,
    )

    # 3. Run detectors (error-isolated per detector)
    if detectors is None:
        # Import detector modules so they register
        _ensure_detectors_loaded()
        if detectors_dir:
            from sentinel.detectors.base import load_custom_detectors
            load_custom_detectors(detectors_dir)
        detectors = get_all_detectors()

    all_findings: list[Finding] = []
    for detector in detectors:
        try:
            logger.info("Running detector: %s", detector.name)
            findings = detector.detect(ctx)
            logger.info("  %s produced %d findings", detector.name, len(findings))
            all_findings.extend(findings)
        except Exception:
            logger.exception("Detector %s failed — skipping", detector.name)

    # 4. Assign fingerprints
    assign_fingerprints(all_findings)

    # 5. Deduplicate
    deduped = deduplicate(all_findings, conn)
    logger.info("After dedup: %d findings (was %d)", len(deduped), len(all_findings))

    # 5b. Build/update embedding index if embed_model is configured
    if embed_model:
        try:
            from sentinel.core.indexer import build_index
            idx_stats = build_index(
                repo_root, conn, embed_model, ollama_url=ollama_url,
                chunk_size=embed_chunk_size, chunk_overlap=embed_chunk_overlap,
            )
            logger.info(
                "Embedding index: %d files indexed, %d chunks",
                idx_stats["files_indexed"], idx_stats["chunks_created"],
            )
        except Exception:
            logger.warning("Embedding index build failed — using heuristic context", exc_info=True)

    # 6. Gather context (with embedding support if configured)
    gather_context(
        deduped, repo_root,
        conn=conn if embed_model else None,
        embed_model=embed_model,
        ollama_url=ollama_url,
    )

    # 7. LLM Judge (optional)
    if not skip_judge:
        deduped = judge_findings(
            deduped, model=model, ollama_url=ollama_url,
            conn=conn, run_id=run.id,
        )
    else:
        logger.info("LLM judge skipped (--skip-judge)")

    # 8. Track finding persistence (occurrence counts)
    fingerprints = [f.fingerprint for f in deduped if f.fingerprint]
    persistence = update_persistence(conn, fingerprints)
    for f in deduped:
        if f.fingerprint in persistence:
            info = persistence[f.fingerprint]
            if f.context is None:
                f.context = {}
            f.context["occurrence_count"] = info.occurrence_count
            f.context["first_seen"] = info.first_seen.isoformat()
            if info.occurrence_count > 1:
                f.context["recurring"] = True

    # 9. Store findings (after persistence so context_json includes occurrence data)
    assert run.id is not None  # guaranteed by create_run
    for f in deduped:
        insert_finding(conn, run.id, f)

    # 10. Complete run
    complete_run(conn, run.id, finding_count=len(deduped))

    # 11. Generate report
    if output_path is None:
        output_path = str(Path(repo_root) / ".sentinel" / f"report-{run.id}.md")

    report = generate_report(deduped, run, output_path=output_path)
    logger.info("Report written to %s", output_path)

    return run, deduped, report


def _ensure_detectors_loaded() -> None:
    """Import all built-in detector modules to trigger registration."""
    import sentinel.detectors.complexity
    import sentinel.detectors.dep_audit
    import sentinel.detectors.docs_drift
    import sentinel.detectors.git_hotspots
    import sentinel.detectors.lint_runner
    import sentinel.detectors.todo_scanner  # noqa: F401


def prepare_incremental(
    repo_path: str, conn: sqlite3.Connection
) -> tuple[ScopeType, list[str] | None]:
    """Determine scope and changed files for an incremental scan.

    Returns (scope, changed_files):
      - If a prior run with a commit SHA exists and files changed: INCREMENTAL + file list
      - Otherwise: FULL + None (falls back to a full scan)
    """
    repo_root = str(Path(repo_path).resolve())
    last_run = get_last_completed_run(conn, repo_root)

    if last_run is None or last_run.commit_sha is None:
        logger.info("No prior run with commit SHA — falling back to full scan")
        return ScopeType.FULL, None

    head = git_head_sha(repo_root)
    if head is None:
        logger.info("Not a git repo — falling back to full scan")
        return ScopeType.FULL, None

    if head == last_run.commit_sha:
        logger.info("HEAD unchanged since last run (%s) — nothing new", head[:8])
        return ScopeType.INCREMENTAL, []

    changed = git_changed_files(repo_root, last_run.commit_sha)
    if changed is None:
        logger.warning(
            "git diff failed (SHA %s may no longer exist) — falling back to full scan",
            last_run.commit_sha[:8],
        )
        return ScopeType.FULL, None

    logger.info(
        "Incremental scan: %d files changed since %s",
        len(changed), last_run.commit_sha[:8],
    )
    return ScopeType.INCREMENTAL, changed
