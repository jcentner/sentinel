"""Pipeline runner — orchestrates the full scan pipeline."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sentinel.core.context import gather_context
from sentinel.core.dedup import assign_fingerprints, deduplicate
from sentinel.core.judge import ajudge_findings, judge_findings
from sentinel.core.provider import ModelProvider
from sentinel.core.report import generate_report
from sentinel.detectors.base import Detector, get_all_detectors
from sentinel.models import (
    CapabilityTier,
    DetectorContext,
    DetectorTier,
    Finding,
    RunSummary,
    ScopeType,
)
from sentinel.store.findings import insert_finding
from sentinel.store.persistence import update_persistence
from sentinel.store.runs import complete_run, create_run, get_last_completed_run

if TYPE_CHECKING:
    from sentinel.config import SentinelConfig

logger = logging.getLogger(__name__)

_TIER_ORDER = {
    CapabilityTier.NONE: 0,
    CapabilityTier.BASIC: 1,
    CapabilityTier.STANDARD: 2,
    CapabilityTier.ADVANCED: 3,
}


def _build_risk_signals(findings: list[Finding]) -> dict[str, dict[str, Any]]:
    """Extract per-file risk signals from heuristic detector findings (TD-043).

    Returns a dict mapping file paths to signal dicts with keys like
    ``is_hotspot``, ``churn_commits``, ``churn_fix_ratio``, ``author_count``.
    """
    signals: dict[str, dict[str, Any]] = {}
    for f in findings:
        if f.file_path is None:
            continue
        if f.detector == "git-hotspots" and isinstance(f.context, dict):
            signals[f.file_path] = {
                "is_hotspot": True,
                "churn_commits": f.context.get("churn_commits", 0),
                "churn_fix_ratio": f.context.get("churn_fix_ratio", 0.0),
                "author_count": f.context.get("author_count", 0),
            }
    return signals


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
    provider: ModelProvider | None = None,
    output_path: str | None = None,
    output_dir: str = ".sentinel",
    skip_judge: bool = False,
    skip_llm: bool = False,
    embed_model: str = "",
    embed_chunk_size: int = 50,
    embed_chunk_overlap: int = 10,
    detectors_dir: str = "",
    num_ctx: int = 2048,
    model_capability: str = "basic",
    min_confidence: float = 0.0,
    enabled_detectors: list[str] | None = None,
    disabled_detectors: list[str] | None = None,
    sentinel_config: SentinelConfig | None = None,
) -> tuple[RunSummary, list[Finding], str]:
    """Execute the full scan pipeline.

    Returns (run_summary, findings, report_text).
    """
    repo_root = str(Path(repo_path).resolve())
    commit_sha = git_head_sha(repo_root)

    # 1. Create run record
    run = create_run(conn, repo_root, scope, commit_sha=commit_sha)
    logger.info("Started run #%d on %s (scope: %s)", run.id, repo_root, scope.value)

    # 2. Build detector context (pass provider to detectors that need LLM)
    ctx = DetectorContext(
        repo_root=repo_root,
        scope=scope,
        changed_files=changed_files,
        target_paths=target_paths,
        config={
            "provider": provider,
            "skip_llm": skip_llm or provider is None,
            "num_ctx": num_ctx,
            "model_capability": model_capability,
        },
        conn=conn,
        run_id=run.id,
    )

    # 3. Run detectors (error-isolated per detector)
    if detectors is None:
        # Import detector modules so they register
        _ensure_detectors_loaded()
        # Discover entry-point detectors (ADR-012)
        from sentinel.detectors.base import load_entrypoint_detectors
        load_entrypoint_detectors()
        if detectors_dir:
            from sentinel.detectors.base import load_custom_detectors
            load_custom_detectors(detectors_dir)
        detectors = get_all_detectors()

    # 3b. Filter detectors by enabled/disabled lists
    if enabled_detectors:
        before_count = len(detectors)
        known_names = {d.name for d in detectors}
        unknown = [n for n in enabled_detectors if n not in known_names]
        if unknown:
            logger.warning("Unknown detector(s) in enabled list: %s", ", ".join(unknown))
        detectors = [d for d in detectors if d.name in enabled_detectors]
        logger.info("Filtered to %d enabled detectors (was %d)", len(detectors), before_count)
    elif disabled_detectors:
        skip_set = set(disabled_detectors)
        before_count = len(detectors)
        detectors = [d for d in detectors if d.name not in skip_set]
        logger.info("Skipping %d disabled detectors (%d remaining)", before_count - len(detectors), len(detectors))

    # 3c. Build per-detector provider cache (OQ-012)
    detector_providers: dict[str, ModelProvider] = {}
    if sentinel_config is not None and not skip_judge:
        from sentinel.core.provider import create_provider_for_detector
        for det in detectors:
            try:
                det_provider = create_provider_for_detector(det.name, sentinel_config)
                if det_provider is not None:
                    detector_providers[det.name] = det_provider
            except ValueError as exc:
                logger.warning(
                    "Could not create per-detector provider for %s: %s — using global",
                    det.name, exc,
                )

    # 3d. Resolve per-detector model_capability overrides
    detector_capabilities: dict[str, str] = {}
    if sentinel_config is not None:
        dp_overrides = getattr(sentinel_config, "detector_providers", {})
        for det_name, override in dp_overrides.items():
            cap = getattr(override, "model_capability", "")
            if cap:
                detector_capabilities[det_name] = cap

    all_findings: list[Finding] = []
    raw_cap = ctx.config.get("model_capability", "basic")
    try:
        model_cap = CapabilityTier(raw_cap)
    except ValueError:
        logger.warning(
            "Unknown model_capability %r — falling back to 'basic'", raw_cap,
        )
        model_cap = CapabilityTier.BASIC

    # TD-043: Two-phase execution — heuristic/deterministic detectors first,
    # then LLM-assisted detectors with risk signals from phase 1.
    phase1 = [d for d in detectors if d.tier != DetectorTier.LLM_ASSISTED]
    phase2 = [d for d in detectors if d.tier == DetectorTier.LLM_ASSISTED]

    def _run_detector(detector: Detector, det_ctx: DetectorContext) -> list[Finding]:
        det_cap = detector.capability_tier
        effective_cap_str = detector_capabilities.get(detector.name, "")
        if effective_cap_str:
            try:
                effective_cap = CapabilityTier(effective_cap_str)
            except ValueError:
                effective_cap = model_cap
        else:
            effective_cap = model_cap

        if _TIER_ORDER.get(det_cap, 0) > _TIER_ORDER.get(effective_cap, 0):
            logger.warning(
                "Detector %s requires %s capability but model is %s — "
                "results may be degraded",
                detector.name, det_cap.value, effective_cap.value,
            )

        det_provider = detector_providers.get(detector.name)
        if det_provider is not None:
            inner_ctx = det_ctx.with_config(
                provider=det_provider,
                skip_llm=False,
                **({"model_capability": effective_cap_str} if effective_cap_str else {}),
            )
        else:
            inner_ctx = det_ctx

        logger.info("Running detector: %s", detector.name)
        findings = detector.detect(inner_ctx)
        n = len(findings)
        logger.info("  %s produced %d %s", detector.name, n, "finding" if n == 1 else "findings")
        return findings

    # Phase 1: Heuristic + deterministic detectors
    for detector in phase1:
        try:
            all_findings.extend(_run_detector(detector, ctx))
        except Exception:
            logger.exception("Detector %s failed — skipping", detector.name)

    # Build risk signals from phase 1 findings for LLM detectors (TD-043)
    risk_signals = _build_risk_signals(all_findings)
    if risk_signals:
        ctx = DetectorContext(
            repo_root=ctx.repo_root,
            scope=ctx.scope,
            changed_files=ctx.changed_files,
            target_paths=ctx.target_paths,
            config=ctx.config,
            conn=ctx.conn,
            run_id=ctx.run_id,
            risk_signals=risk_signals,
        )
        logger.info("Risk signals built for %d files from phase 1", len(risk_signals))

    # Phase 2: LLM-assisted detectors (with risk signals available)
    for detector in phase2:
        try:
            all_findings.extend(_run_detector(detector, ctx))
        except Exception:
            logger.exception("Detector %s failed — skipping", detector.name)

    # 4. Assign fingerprints
    assign_fingerprints(all_findings)

    # 5. Deduplicate
    deduped = deduplicate(all_findings, conn)
    logger.info("After dedup: %d findings (was %d)", len(deduped), len(all_findings))

    # 5b. Build/update embedding index if embed_model is configured and provider supports embedding
    if embed_model and provider is not None:
        try:
            from sentinel.core.indexer import build_index
            idx_stats = build_index(
                repo_root, conn, provider,
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
        provider=provider if embed_model else None,
        conn=conn if embed_model else None,
    )

    # 7. LLM Judge (optional — async with bounded concurrency, ADR-017)
    if not skip_judge and provider is not None:
        deduped = asyncio.run(ajudge_findings(
            deduped, provider=provider,
            conn=conn, run_id=run.id, num_ctx=num_ctx,
        ))
    else:
        logger.info("LLM judge skipped (--skip-judge or no provider)")

    # 7b. Finding cluster synthesis (requires standard+ capability, async ADR-017)
    if not skip_judge and provider is not None:
        if _TIER_ORDER.get(model_cap, 0) >= _TIER_ORDER[CapabilityTier.STANDARD]:
            from sentinel.core.synthesis import asynthesize_clusters
            logger.info("Running finding cluster synthesis (capability: %s)", model_cap.value)
            deduped = asyncio.run(asynthesize_clusters(
                deduped, provider=provider,
                conn=conn, run_id=run.id, num_ctx=num_ctx,
            ))
        else:
            logger.info("Cluster synthesis skipped (requires standard+ capability, have %s)", model_cap.value)

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

    # 11. Generate report (filter low-confidence findings for readability)
    report_findings = deduped
    if min_confidence > 0:
        report_findings = [f for f in deduped if f.confidence >= min_confidence]
        filtered_count = len(deduped) - len(report_findings)
        if filtered_count:
            logger.info(
                "Filtered %d findings below confidence threshold %.0f%%",
                filtered_count, min_confidence * 100,
            )

    if output_path is None:
        output_path = str(Path(repo_root) / output_dir / f"report-{run.id}.md")

    report = generate_report(report_findings, run, output_path=output_path)
    logger.info("Report written to %s", output_path)

    return run, deduped, report


def _ensure_detectors_loaded() -> None:
    """Import all built-in detector modules to trigger registration.

    Uses pkgutil to discover modules in the sentinel.detectors package
    dynamically, so adding a new detector file requires no changes here.
    """
    import importlib
    import pkgutil

    import sentinel.detectors as det_pkg

    for _finder, module_name, _is_pkg in pkgutil.iter_modules(det_pkg.__path__):
        if module_name.startswith("_"):
            continue
        full_name = f"sentinel.detectors.{module_name}"
        try:
            importlib.import_module(full_name)
        except Exception:
            logger.warning("Failed to import detector module %s", full_name, exc_info=True)


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
