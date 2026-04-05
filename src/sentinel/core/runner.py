"""Pipeline runner — orchestrates the full scan pipeline."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from sentinel.core.context import gather_context
from sentinel.core.dedup import assign_fingerprints, deduplicate
from sentinel.core.judge import judge_findings
from sentinel.core.report import generate_report
from sentinel.detectors.base import Detector, get_all_detectors
from sentinel.models import DetectorContext, Finding, RunSummary, ScopeType
from sentinel.store.findings import insert_finding
from sentinel.store.persistence import update_persistence
from sentinel.store.runs import complete_run, create_run

logger = logging.getLogger(__name__)


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
) -> tuple[RunSummary, list[Finding], str]:
    """Execute the full scan pipeline.

    Returns (run_summary, findings, report_text).
    """
    repo_root = str(Path(repo_path).resolve())

    # 1. Create run record
    run = create_run(conn, repo_root, scope)
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
    )

    # 3. Run detectors (error-isolated per detector)
    if detectors is None:
        # Import detector modules so they register
        _ensure_detectors_loaded()
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

    # 6. Gather context
    gather_context(deduped, repo_root)

    # 7. LLM Judge (optional)
    if not skip_judge:
        deduped = judge_findings(deduped, model=model, ollama_url=ollama_url)
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
    import sentinel.detectors.dep_audit
    import sentinel.detectors.docs_drift
    import sentinel.detectors.git_hotspots
    import sentinel.detectors.lint_runner
    import sentinel.detectors.todo_scanner  # noqa: F401
