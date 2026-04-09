"""CLI entry point for Sentinel."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from sentinel import __version__

if TYPE_CHECKING:
    from sentinel.config import SentinelConfig


@click.group()
@click.version_option(version=__version__, prog_name="sentinel")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.option("-q", "--quiet", is_flag=True, help="Suppress log output below ERROR level")
@click.pass_context
def main(ctx: click.Context, verbose: bool, quiet: bool) -> None:
    """Local Repo Sentinel — overnight code health monitoring.

    Exit codes: 0 = success, 1 = error, 2 = partial failure (scan-all).
    Most subcommands support --json-output for machine-readable output.
    """
    if verbose and quiet:
        raise click.UsageError("Cannot use --verbose and --quiet together.")
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--model", default=None, help="Model name")
@click.option("--ollama-url", default=None, help="Ollama API URL")
@click.option("--provider", "provider_name", default=None, help="Model provider: ollama (default), openai, or azure")
@click.option("--api-base", default=None, help="API base URL for openai provider")
@click.option("--output", "-o", default=None, help="Report output path")
@click.option("--skip-judge", is_flag=True, help="Skip LLM judge (use raw findings)")
@click.option("--db", default=None, help="Database path")
@click.option(
    "--incremental", is_flag=True,
    help="Only scan files changed since the last completed run",
)
@click.option("--embed-model", default=None, help="Embedding model (enables semantic context)")
@click.option("--target", "-t", multiple=True, help="Scan only specific paths (repeatable)")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
@click.option("--detectors", "detector_names", default=None, help="Comma-separated list of detectors to run (overrides config)")
@click.option("--skip-detectors", "skip_detector_names", default=None, help="Comma-separated list of detectors to skip (overrides config)")
@click.option("--capability", "capability", default=None, help="Model capability tier: none, basic, standard, advanced")
def scan(
    repo_path: str,
    model: str | None,
    ollama_url: str | None,
    provider_name: str | None,
    api_base: str | None,
    output: str | None,
    skip_judge: bool,
    db: str | None,
    incremental: bool,
    embed_model: str | None,
    target: tuple[str, ...],
    output_json: bool,
    detector_names: str | None,
    skip_detector_names: str | None,
    capability: str | None,
) -> None:
    """Run detectors against a repository and generate a morning report."""
    from sentinel.config import load_config
    from sentinel.store.db import get_connection

    repo = Path(repo_path).resolve()
    config = load_config(repo)
    _apply_cli_overrides(config, model, ollama_url, skip_judge, embed_model,
                         provider_name=provider_name, api_base=api_base,
                         detector_names=detector_names,
                         skip_detector_names=skip_detector_names,
                         capability=capability)

    db_path = db or str(repo / config.db_path)
    conn = get_connection(db_path)

    try:
        scope_result = _resolve_scope(str(repo), conn, incremental, list(target) if target else None)
        if scope_result is None:
            click.echo("No changes since last run — nothing to scan.")
            return

        run, findings, _report = _execute_scan(str(repo), conn, config, scope_result, output)
        actual_path = output or str(repo / config.output_dir / f"report-{run.id}.md")

        if output_json:
            click.echo(json.dumps({
                "run": run.to_dict(),
                "findings": [f.to_dict() for f in findings],
                "report_path": actual_path,
            }, indent=2))
        else:
            click.echo(f"Scan complete: {len(findings)} findings in run #{run.id}")
            if findings:
                from collections import Counter
                sev_counts = Counter(f.severity.value for f in findings)
                parts = []
                for sev in ("critical", "high", "medium", "low"):
                    if sev in sev_counts:
                        parts.append(f"{sev_counts[sev]} {sev}")
                click.echo(f"  Severity: {', '.join(parts)}")
            if incremental and scope_result.get("changed_files"):
                click.echo(f"Incremental: {len(scope_result['changed_files'])} files changed since last run")
            click.echo(f"Report: {actual_path}")
    finally:
        conn.close()


def _apply_cli_overrides(
    config: SentinelConfig,
    model: str | None,
    ollama_url: str | None,
    skip_judge: bool,
    embed_model: str | None,
    *,
    provider_name: str | None = None,
    api_base: str | None = None,
    detector_names: str | None = None,
    skip_detector_names: str | None = None,
    capability: str | None = None,
) -> None:
    """Apply CLI flag overrides to a loaded config."""
    if provider_name:
        config.provider = provider_name
    if model:
        config.model = model
    if ollama_url:
        config.ollama_url = ollama_url
    if api_base:
        config.api_base = api_base
    if skip_judge:
        config.skip_judge = True
    if embed_model:
        config.embed_model = embed_model
    if detector_names:
        config.enabled_detectors = [d.strip() for d in detector_names.split(",") if d.strip()]
    if skip_detector_names:
        config.disabled_detectors = [d.strip() for d in skip_detector_names.split(",") if d.strip()]
    if capability:
        from sentinel.config import _VALID_CAPABILITIES
        if capability not in _VALID_CAPABILITIES:
            raise click.UsageError(
                f"--capability must be one of {sorted(_VALID_CAPABILITIES)}, got {capability!r}"
            )
        config.model_capability = capability
    if config.enabled_detectors and config.disabled_detectors:
        raise click.UsageError("Cannot use both --detectors and --skip-detectors")


def _resolve_scope(
    repo: str,
    conn: sqlite3.Connection,
    incremental: bool,
    target_paths: list[str] | None,
) -> dict[str, Any] | None:
    """Determine scan scope. Returns None if incremental with no changes."""
    from sentinel.core.runner import prepare_incremental
    from sentinel.models import ScopeType

    if incremental and target_paths:
        raise click.UsageError("Cannot use --incremental and --target together.")

    result: dict[str, Any] = {}
    if target_paths:
        result["scope"] = ScopeType.TARGETED
        result["target_paths"] = target_paths
    elif incremental:
        scope_type, changed_files = prepare_incremental(repo, conn)
        if scope_type == ScopeType.INCREMENTAL and changed_files is not None and len(changed_files) == 0:
            return None
        result["scope"] = scope_type
        if changed_files is not None:
            result["changed_files"] = changed_files
    return result


def _execute_scan(
    repo: str,
    conn: sqlite3.Connection,
    config: SentinelConfig,
    scope_result: dict[str, Any],
    output_path: str | None,
) -> Any:
    """Execute the scan with resolved config and scope."""
    from sentinel.core.provider import create_provider
    from sentinel.core.runner import run_scan

    # Create the model provider from config (None if judge is skipped)
    provider = None
    if not config.skip_judge:
        try:
            provider = create_provider(config)
        except ValueError as exc:
            logging.getLogger(__name__).warning(
                "Could not create model provider: %s — running without LLM", exc,
            )

    kwargs: dict[str, Any] = dict(
        provider=provider,
        skip_judge=config.skip_judge,
        embed_model=config.embed_model,
        embed_chunk_size=config.embed_chunk_size,
        embed_chunk_overlap=config.embed_chunk_overlap,
        detectors_dir=config.detectors_dir,
        output_dir=config.output_dir,
        num_ctx=config.num_ctx,
        model_capability=config.model_capability,
        enabled_detectors=config.enabled_detectors or None,
        disabled_detectors=config.disabled_detectors or None,
        sentinel_config=config if config.detector_providers else None,
    )
    if output_path is not None:
        kwargs["output_path"] = output_path
    if "scope" in scope_result:
        kwargs["scope"] = scope_result["scope"]
    if "changed_files" in scope_result:
        kwargs["changed_files"] = scope_result["changed_files"]
    if "target_paths" in scope_result:
        kwargs["target_paths"] = scope_result["target_paths"]

    return run_scan(repo, conn, **kwargs)


@main.command()
@click.argument("finding_id", type=int)
@click.option("--reason", "-r", default=None, help="Reason for suppression")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def suppress(finding_id: int, reason: str | None, repo: str, db: str | None, output_json: bool) -> None:
    """Suppress a finding by its ID (exclude from future reports)."""
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.findings import get_finding_by_id, suppress_finding

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        finding = get_finding_by_id(conn, finding_id)
        if finding is None:
            if output_json:
                click.echo(json.dumps({"error": f"Finding #{finding_id} not found"}))
            else:
                click.echo(f"Finding #{finding_id} not found.", err=True)
            raise SystemExit(1)

        suppress_finding(conn, finding.fingerprint, reason=reason)
        if output_json:
            click.echo(json.dumps({
                "id": finding_id,
                "fingerprint": finding.fingerprint,
                "title": finding.title,
                "status": "suppressed",
                "reason": reason,
            }))
        else:
            click.echo(f"Suppressed finding #{finding_id}: {finding.title}")
    finally:
        conn.close()


@main.command()
@click.argument("finding_id", type=int)
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def approve(finding_id: int, repo: str, db: str | None, output_json: bool) -> None:
    """Approve a finding (mark it for GitHub issue creation)."""
    from sentinel.config import load_config
    from sentinel.models import FindingStatus
    from sentinel.store.db import get_connection
    from sentinel.store.findings import get_finding_by_id, update_finding_status

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        finding = get_finding_by_id(conn, finding_id)
        if finding is None:
            if output_json:
                click.echo(json.dumps({"error": f"Finding #{finding_id} not found"}))
            else:
                click.echo(f"Finding #{finding_id} not found.", err=True)
            raise SystemExit(1)

        update_finding_status(conn, finding_id, FindingStatus.APPROVED)
        if output_json:
            click.echo(json.dumps({
                "id": finding_id,
                "fingerprint": finding.fingerprint,
                "title": finding.title,
                "status": "approved",
            }))
        else:
            click.echo(f"Approved finding #{finding_id}: {finding.title}")
            click.echo("Run 'sentinel create-issues' to create GitHub issues from approved findings.")
    finally:
        conn.close()


@main.command()
@click.argument("finding_id", type=int)
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def show(finding_id: int, repo: str, db: str | None, output_json: bool) -> None:
    """Show full details of a finding by its ID."""
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.findings import get_finding_by_id

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        finding = get_finding_by_id(conn, finding_id)
        if finding is None:
            if output_json:
                click.echo(json.dumps({"error": f"Finding #{finding_id} not found"}))
            else:
                click.echo(f"Finding #{finding_id} not found.", err=True)
            raise SystemExit(1)

        if output_json:
            click.echo(json.dumps(finding.to_dict(), indent=2))
        else:
            click.echo(f"Finding #{finding_id}")
            click.echo(f"  Title:       {finding.title}")
            click.echo(f"  Detector:    {finding.detector}")
            click.echo(f"  Category:    {finding.category}")
            click.echo(f"  Severity:    {finding.severity.value}")
            click.echo(f"  Confidence:  {finding.confidence:.0%}")
            click.echo(f"  Status:      {finding.status.value}")
            click.echo(f"  Fingerprint: {finding.fingerprint}")
            if finding.file_path:
                loc = finding.file_path
                if finding.line_start:
                    loc += f":{finding.line_start}"
                    if finding.line_end and finding.line_end != finding.line_start:
                        loc += f"-{finding.line_end}"
                click.echo(f"  Location:    {loc}")
            click.echo(f"  Description: {finding.description}")

            if finding.evidence:
                click.echo("")
                click.echo("  Evidence:")
                for i, ev in enumerate(finding.evidence, 1):
                    click.echo(f"    [{i}] {ev.type.value}: {ev.source}")
                    for line in ev.content.splitlines():
                        click.echo(f"        {line}")

            if finding.context:
                occ = finding.context.get("occurrence_count")
                if occ and occ > 1:
                    first_seen = finding.context.get("first_seen", "?")
                    click.echo(f"\n  Recurring: seen {occ} times (first: {first_seen})")
    finally:
        conn.close()


@main.command("create-issues")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--owner", default=None, help="GitHub repo owner (or SENTINEL_GITHUB_OWNER env)")
@click.option("--github-repo", default=None, help="GitHub repo name (or SENTINEL_GITHUB_REPO env)")
@click.option("--token", default=None, help="GitHub token (prefer SENTINEL_GITHUB_TOKEN env to avoid shell history leaks)")
@click.option("--dry-run", is_flag=True, help="Show what would be created without making API calls")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def create_issues_cmd(
    repo: str,
    db: str | None,
    owner: str | None,
    github_repo: str | None,
    token: str | None,
    dry_run: bool,
    output_json: bool,
) -> None:
    """Create GitHub issues from approved findings.

    Requires GitHub token via --token or SENTINEL_GITHUB_TOKEN env var.
    Deduplicates against existing open issues with sentinel labels.
    """
    from sentinel.config import load_config
    from sentinel.github import create_issues, get_approved_findings, get_github_config
    from sentinel.store.db import get_connection

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    gh = get_github_config(owner=owner, repo=github_repo, token=token)
    if gh is None and not dry_run:
        click.echo(
            "GitHub config required. Set --owner, --github-repo, --token "
            "or SENTINEL_GITHUB_OWNER, SENTINEL_GITHUB_REPO, SENTINEL_GITHUB_TOKEN env vars.",
            err=True,
        )
        raise SystemExit(1)

    conn = get_connection(db_path)
    try:
        approved = get_approved_findings(conn)
        if not approved:
            if output_json:
                click.echo(json.dumps({"results": [], "message": "No approved findings"}))
            else:
                click.echo("No approved findings to create issues for.")
            return

        if not output_json:
            click.echo(f"Found {len(approved)} approved finding(s)")

        if dry_run and gh is None:
            # dry run without GitHub config — just show what would be created
            if output_json:
                click.echo(json.dumps({"results": [
                    {"fingerprint": f.fingerprint, "title": f.title, "dry_run": True}
                    for _db_id, f in approved
                ]}))
            else:
                for _db_id, finding in approved:
                    click.echo(f"  [DRY RUN] Would create: [Sentinel] {finding.title}")
            return

        assert gh is not None  # non-dry-run checked above; dry-run returned above
        results = create_issues(conn, gh, dry_run=dry_run)

        if output_json:
            click.echo(json.dumps({"results": [
                {
                    "fingerprint": r.fingerprint,
                    "success": r.success,
                    "issue_url": r.issue_url,
                    "error": r.error,
                }
                for r in results
            ]}, indent=2))
        else:
            for r in results:
                if r.success:
                    if r.issue_url:
                        click.echo(f"  ✓ {r.fingerprint} → {r.issue_url}")
                    elif r.error == "dry run":
                        click.echo(f"  [DRY RUN] {r.fingerprint}")
                    else:
                        click.echo(f"  ✓ {r.fingerprint}")
                else:
                    click.echo(f"  ✗ {r.fingerprint}: {r.error}")

            success_count = sum(1 for r in results if r.success)
            click.echo(f"\n{success_count}/{len(results)} issues created successfully")
    finally:
        conn.close()


@main.command()
@click.option("--run", "run_id", type=int, default=None, help="Show findings for a specific run ID")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--detector", default=None, help="Filter by detector name")
@click.option("--severity", default=None, type=click.Choice(["low", "medium", "high", "critical"]),
              help="Filter by minimum severity")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def findings(
    run_id: int | None,
    repo: str,
    db: str | None,
    detector: str | None,
    severity: str | None,
    output_json: bool,
) -> None:
    """List findings from a scan run.

    If --run is not specified, shows findings from the most recent run.
    """
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.findings import get_findings_by_run
    from sentinel.store.runs import get_run_history

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        if run_id is None:
            runs = get_run_history(conn, limit=1)
            if not runs:
                if output_json:
                    click.echo(json.dumps({"error": "No runs found"}))
                else:
                    click.echo("No runs found.", err=True)
                raise SystemExit(1)
            run_id = runs[0].id

        results = get_findings_by_run(conn, run_id)

        # Apply filters
        if detector:
            results = [f for f in results if f.detector == detector]
        if severity:
            sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            min_sev = sev_order.get(severity, 0)
            results = [
                f for f in results
                if sev_order.get(f.severity.value, 0) >= min_sev
            ]

        if output_json:
            click.echo(json.dumps([f.to_dict() for f in results], indent=2))
        else:
            if not results:
                click.echo(f"No findings for run #{run_id}.")
                return

            click.echo(f"Findings for run #{run_id} ({len(results)} total):\n")
            click.echo(f"{'ID':>5}  {'Severity':<9}  {'Detector':<20}  {'Title'}")
            click.echo("-" * 80)
            for f in results:
                click.echo(
                    f"{f.id:>5}  {f.severity.value:<9}  {f.detector:<20}  {f.title[:40]}"
                )
    finally:
        conn.close()


@main.command()
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--limit", "-n", default=20, help="Number of runs to show")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def history(repo: str, db: str | None, limit: int, output_json: bool) -> None:
    """Show past scan runs."""
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.runs import get_run_history

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        runs = get_run_history(conn, limit=limit)
        if not runs:
            if output_json:
                click.echo(json.dumps([]))
            else:
                click.echo("No runs found.")
            return

        if output_json:
            click.echo(json.dumps([r.to_dict() for r in runs], indent=2))
        else:
            click.echo(f"{'ID':>4}  {'Scope':<12}  {'Findings':>8}  {'Started':>20}  {'Repo'}")
            click.echo("-" * 80)
            for r in runs:
                started = r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "?"
                click.echo(
                    f"{r.id:>4}  {r.scope.value:<12}  {r.finding_count:>8}  {started:>20}  {r.repo_path}"
                )
    finally:
        conn.close()


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--embed-model", default=None,
              help="Embedding model (default: from config or nomic-embed-text)")
@click.option("--ollama-url", default=None, help="Ollama API URL")
@click.option("--db", default=None, help="Database path")
@click.option("--clear", is_flag=True, help="Clear existing index before rebuilding")
def index(
    repo_path: str,
    embed_model: str | None,
    ollama_url: str | None,
    db: str | None,
    clear: bool,
) -> None:
    """Build or update the embedding index for semantic context.

    Chunks repo files and embeds them via model provider for use during scan.
    Only re-embeds files that have changed since the last index build.
    """
    from sentinel.config import load_config
    from sentinel.core.indexer import build_index
    from sentinel.core.provider import create_provider
    from sentinel.store.db import get_connection
    from sentinel.store.embeddings import chunk_count, clear_all_chunks

    repo = Path(repo_path).resolve()
    config = load_config(repo)

    if ollama_url:
        config.ollama_url = ollama_url

    # Resolve embed model: CLI flag > config > default
    resolved_model = embed_model or config.embed_model or "nomic-embed-text"
    config.embed_model = resolved_model

    db_path = db or str(repo / config.db_path)
    conn = get_connection(db_path)

    try:
        provider = create_provider(config)

        if clear:
            cleared = clear_all_chunks(conn)
            click.echo(f"Cleared {cleared} existing chunks")

        click.echo(f"Building embedding index with model '{resolved_model}'...")
        stats = build_index(
            str(repo), conn, provider,
            chunk_size=config.embed_chunk_size,
            chunk_overlap=config.embed_chunk_overlap,
        )

        click.echo(f"  Files scanned: {stats['files_scanned']}")
        click.echo(f"  Files indexed: {stats['files_indexed']}")
        click.echo(f"  Files skipped: {stats['files_skipped']}")
        click.echo(f"  Files removed: {stats['files_removed']}")
        click.echo(f"  Chunks created: {stats['chunks_created']}")
        click.echo(f"  Total chunks: {chunk_count(conn)}")
    finally:
        conn.close()


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--ground-truth", "-g", default=None, type=click.Path(exists=True),
              help="Path to ground-truth.toml file (default: <repo>/ground-truth.toml)")
@click.option("--db", default=None, help="Database path")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def eval(
    repo_path: str,
    ground_truth: str | None,
    db: str | None,
    output_json: bool,
) -> None:
    """Evaluate detector precision/recall against annotated ground truth.

    Runs all detectors on REPO_PATH and compares results to GROUND_TRUTH.
    Prints precision, recall, and details of mismatches.
    """
    from sentinel.core.eval import evaluate, load_ground_truth
    from sentinel.core.runner import run_scan
    from sentinel.store.db import get_connection
    from sentinel.store.eval_store import save_eval_result

    repo = Path(repo_path).resolve()

    # Find ground truth file
    gt_path = Path(ground_truth) if ground_truth else repo / "ground-truth.toml"
    if not gt_path.exists():
        click.echo(f"Ground truth file not found: {gt_path}", err=True)
        click.echo("Create a ground-truth.toml file or use --ground-truth to specify one.", err=True)
        raise SystemExit(1)

    gt = load_ground_truth(gt_path)

    # Use the real DB if specified, otherwise default to the repo's configured DB
    # so eval results persist across runs
    if db:
        db_actual = db
    else:
        from sentinel.config import load_config
        config = load_config(repo)
        db_actual = str(repo / config.db_path)

    conn = get_connection(db_actual)
    try:
        _, findings, _ = run_scan(
            str(repo), conn, skip_judge=True, output_path="/dev/null",
        )

        result = evaluate(findings, gt)
        passed = result.precision >= 0.70 and result.recall >= 0.90

        # Persist eval result
        save_eval_result(
            conn,
            repo_path=str(repo),
            total_findings=result.total_findings,
            true_positives=result.true_positives,
            false_positives_found=result.false_positives_found,
            missing_count=len(result.missing),
            precision=result.precision,
            recall=result.recall,
            ground_truth_path=str(gt_path),
            details={
                "missing": result.missing,
                "unexpected_fps": result.unexpected_fps,
            },
        )
    finally:
        conn.close()

    if output_json:
        data = result.to_dict()
        data["repo"] = str(repo)
        data["passed"] = passed
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo("")
        click.echo("═══ Sentinel Evaluation ═══")
        click.echo(f"Repo:     {repo}")
        click.echo(f"Findings: {result.total_findings}")
        click.echo(f"TP:       {result.true_positives}")
        click.echo(f"Missing:  {len(result.missing)}")
        click.echo(f"FP found: {result.false_positives_found}")
        click.echo("")
        click.echo(f"Precision: {result.precision:.0%}")
        click.echo(f"Recall:    {result.recall:.0%}")

        if result.missing:
            click.echo("")
            click.echo("Missing expected findings:")
            for m in result.missing:
                click.echo(f"  - [{m['detector']}] {m.get('file_path', '?')} / {m.get('title', '?')}")

        if result.unexpected_fps:
            click.echo("")
            click.echo("Known false positives that appeared:")
            for fp in result.unexpected_fps:
                click.echo(f"  - {fp}")

        if passed:
            click.echo("")
            click.echo("✓ PASS — meets ADR-008 targets (precision ≥70%, recall ≥90%)")
        else:
            click.echo("")
            click.echo("✗ FAIL — below ADR-008 targets")

    if not passed:
        raise SystemExit(1)


@main.command("eval-history")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--limit", "-n", default=20, help="Number of results to show")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def eval_history(repo: str, db: str | None, limit: int, output_json: bool) -> None:
    """Show past evaluation results with precision/recall trends."""
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.eval_store import get_eval_history

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        results = get_eval_history(conn, repo_path=str(repo_path), limit=limit)
        if not results:
            if output_json:
                click.echo(json.dumps([]))
            else:
                click.echo("No evaluation results found.")
            return

        if output_json:
            click.echo(json.dumps([r.to_dict() for r in results], indent=2))
        else:
            click.echo(f"{'#':>4}  {'Date':>20}  {'Findings':>8}  {'TP':>4}  {'FP':>4}  {'Prec':>6}  {'Recall':>6}")
            click.echo("-" * 70)
            for r in results:
                date_str = r.evaluated_at.strftime("%Y-%m-%d %H:%M") if r.evaluated_at else "?"
                click.echo(
                    f"{r.id or 0:>4}  {date_str:>20}  {r.total_findings:>8}  "
                    f"{r.true_positives:>4}  {r.false_positives_found:>4}  "
                    f"{r.precision:>5.0%}  {r.recall:>5.0%}"
                )
    finally:
        conn.close()


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--host", default="127.0.0.1", help="Bind address (default: localhost only)")
@click.option("--port", default=8888, type=int, help="Port number")
@click.option("--db", default=None, help="Database path")
def serve(
    repo_path: str,
    host: str,
    port: int,
    db: str | None,
) -> None:
    """Start the local web UI for reviewing scan results.

    Launches a browser-based interface on localhost for browsing
    runs, reviewing findings, and approving/suppressing issues.
    Requires the [web] optional dependency group.
    """
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "Web UI dependencies not installed. Run: pip install sentinel[web]",
            err=True,
        )
        raise SystemExit(1) from None

    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.web.app import create_app

    repo = Path(repo_path).resolve()
    config = load_config(repo)
    db_path = db or str(repo / config.db_path)
    conn = get_connection(db_path, check_same_thread=False)

    app = create_app(conn, repo_path=str(repo))
    click.echo(f"Sentinel web UI: http://{host}:{port}")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        conn.close()


@main.command("scan-all")
@click.argument("repo_paths", nargs=-1, required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--db", required=True, help="Shared database path for all repos")
@click.option("--skip-judge", is_flag=True, help="Skip LLM judge (use raw findings)")
@click.option("--model", default=None, help="Model name (overrides per-repo config)")
@click.option("--ollama-url", default=None, help="Ollama API URL (overrides per-repo config)")
@click.option("--provider", "provider_name", default=None, help="Model provider (overrides per-repo config)")
@click.option("--api-base", default=None, help="API base URL for openai provider")
@click.option("--embed-model", default=None, help="Embedding model (overrides per-repo config)")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
@click.option("--detectors", "detector_names", default=None, help="Comma-separated list of detectors to run")
@click.option("--skip-detectors", "skip_detector_names", default=None, help="Comma-separated list of detectors to skip")
@click.option("--capability", "capability", default=None, help="Model capability tier: none, basic, standard, advanced")
def scan_all(
    repo_paths: tuple[str, ...],
    db: str,
    skip_judge: bool,
    model: str | None,
    ollama_url: str | None,
    provider_name: str | None,
    api_base: str | None,
    embed_model: str | None,
    output_json: bool,
    detector_names: str | None,
    skip_detector_names: str | None,
    capability: str | None,
) -> None:
    """Scan multiple repositories into a shared database.

    Each repo is scanned independently. All results go into the same
    database, accessible via 'sentinel serve' or 'sentinel history'.

    \b
    Example:
        sentinel scan-all ~/project-a ~/project-b --db ~/.sentinel/all.db
    """
    from sentinel.config import load_config
    from sentinel.store.db import get_connection

    conn = get_connection(db)
    results: list[dict[str, Any]] = []
    had_errors = False

    try:
        for repo_path in repo_paths:
            repo = Path(repo_path).resolve()
            try:
                config = load_config(repo)
                _apply_cli_overrides(config, model, ollama_url, skip_judge, embed_model,
                                     provider_name=provider_name, api_base=api_base,
                                     detector_names=detector_names,
                                     skip_detector_names=skip_detector_names,
                                     capability=capability)
                run, findings, _report = _execute_scan(str(repo), conn, config, {}, None)
                results.append({
                    "repo": str(repo),
                    "run_id": run.id,
                    "findings": len(findings),
                    "status": "ok",
                })
                if not output_json:
                    click.echo(f"  {repo}: {len(findings)} findings (run #{run.id})")
            except (OSError, RuntimeError, ValueError) as e:
                had_errors = True
                results.append({
                    "repo": str(repo),
                    "error": str(e),
                    "status": "error",
                })
                if not output_json:
                    click.echo(f"  {repo}: ERROR — {e}", err=True)

        if output_json:
            click.echo(json.dumps({"results": results}, indent=2))
        else:
            total = sum(r.get("findings", 0) for r in results)
            ok = sum(1 for r in results if r["status"] == "ok")
            click.echo(f"\nScanned {ok}/{len(repo_paths)} repos, {total} total findings")
            click.echo(f"Database: {db}")
    finally:
        conn.close()

    if had_errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()


# Profile definitions: name → (model_capability, detector_filter_fn, description)
_PROFILES = {
    "minimal": {
        "description": "Heuristic-only detectors, no LLM required",
        "model_capability": "none",
        "skip_judge": True,
        "filter": lambda tier: tier == "none",
    },
    "standard": {
        "description": "All detectors with basic LLM support",
        "model_capability": "basic",
        "skip_judge": False,
        "filter": lambda tier: True,
    },
    "full": {
        "description": "All detectors with enhanced LLM analysis",
        "model_capability": "standard",
        "skip_judge": False,
        "filter": lambda tier: True,
    },
}


def _build_init_config(
    *,
    profile: str | None = None,
    detector_names: list[str] | None = None,
) -> str:
    """Build a sentinel.toml config string based on profile or detector selection."""
    from sentinel.detectors.base import get_detector_info

    all_detectors = sorted(get_detector_info(), key=lambda d: d["name"])

    # Determine which detectors to enable
    if detector_names:
        enabled = detector_names
        cap = "basic"
        skip = False
    elif profile and profile in _PROFILES:
        p = _PROFILES[profile]
        enabled = [d["name"] for d in all_detectors if p["filter"](d["tier"])]
        cap = p["model_capability"]
        skip = p["skip_judge"]
    else:
        # Default: all detectors, basic capability
        enabled = [d["name"] for d in all_detectors]
        cap = "basic"
        skip = False

    # Build the config
    lines = [
        "# Sentinel configuration",
        "# Generated by: sentinel init",
        "#",
        "# Available detectors and their capability tiers:",
    ]
    for d in all_detectors:
        marker = "✓" if d["name"] in enabled else "✗"
        lines.append(f"#   {marker} {d['name']:20s} (tier: {d['tier']:8s}) — {d['description'][:60]}")
    lines.append("")

    lines.append("[sentinel]")
    lines.append('# Model provider: "ollama" (default, local) or "openai" (OpenAI-compatible API)')
    lines.append('provider = "ollama"')
    lines.append("")
    lines.append("# LLM model for judge + detectors")
    lines.append('model = "qwen3.5:4b"')
    lines.append('ollama_url = "http://localhost:11434"')
    lines.append(f"skip_judge = {'true' if skip else 'false'}")
    lines.append(f'model_capability = "{cap}"')
    lines.append("")
    lines.append('# For OpenAI-compatible providers (Azure OpenAI, OpenAI, vLLM, LM Studio):')
    lines.append('# provider = "openai"')
    lines.append('# model = "gpt-5.4-nano"')
    lines.append('# api_base = "https://api.openai.com"')
    lines.append('# api_key_env = "OPENAI_API_KEY"')
    lines.append("")
    lines.append("# Embedding model for semantic context (leave empty to disable)")
    lines.append("# embed_model = \"nomic-embed-text\"")
    lines.append("")
    lines.append("# Database and output directory (relative to repo root)")
    lines.append('db_path = ".sentinel/sentinel.db"')
    lines.append('output_dir = ".sentinel"')
    lines.append("")
    lines.append("# Custom detectors directory (leave empty for built-in only)")
    lines.append("# detectors_dir = \"\"")
    lines.append("")
    lines.append("# LLM context window size (tokens)")
    lines.append("# num_ctx = 2048")
    lines.append("")
    lines.append("# Enabled detectors (remove entries to disable)")
    lines.append("enabled_detectors = [")
    for name in enabled:
        lines.append(f'    "{name}",')
    lines.append("]")
    lines.append("")

    return "\n".join(lines)


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--force", is_flag=True, help="Overwrite existing sentinel.toml")
@click.option(
    "--profile",
    type=click.Choice(["minimal", "standard", "full"]),
    help="Detector profile: minimal (no LLM), standard (all detectors), full (enhanced analysis)",
)
@click.option("--detectors", "detector_str", help="Comma-separated list of detectors to enable")
@click.option("--list-detectors", is_flag=True, help="List available detectors and exit")
def init(repo_path: str, force: bool, profile: str | None, detector_str: str | None, list_detectors: bool) -> None:
    """Initialize a sentinel.toml config file in a repository.

    Creates a sentinel.toml with documented defaults. Also
    creates the .sentinel directory and adds it to .gitignore.

    Use --profile to select a preset configuration:
      minimal  — heuristic-only detectors, no LLM required
      standard — all detectors with basic LLM support
      full     — all detectors with enhanced LLM analysis

    Use --detectors to explicitly choose which detectors to enable.
    Use --list-detectors to see all available detectors.
    """
    if list_detectors:
        from sentinel.detectors.base import get_detector_info
        detectors = sorted(get_detector_info(), key=lambda d: d["name"])
        click.echo("Available detectors:\n")
        for d in detectors:
            click.echo(f"  {d['name']:20s}  tier: {d['tier']:8s}  {d['description'][:60]}")
        click.echo(f"\n{len(detectors)} detectors available.")
        click.echo("\nProfiles:")
        for name, p in _PROFILES.items():
            count = sum(1 for d in detectors if p["filter"](d["tier"]))
            click.echo(f"  {name:10s}  {count:2d} detectors — {p['description']}")
        return

    if profile and detector_str:
        raise click.UsageError("Cannot use --profile and --detectors together.")

    detector_names = None
    if detector_str:
        detector_names = [d.strip() for d in detector_str.split(",") if d.strip()]

    repo = Path(repo_path).resolve()
    config_path = repo / "sentinel.toml"

    if config_path.exists() and not force:
        click.echo(f"sentinel.toml already exists at {config_path}", err=True)
        click.echo("Use --force to overwrite.", err=True)
        raise SystemExit(1)

    config_content = _build_init_config(profile=profile, detector_names=detector_names)
    config_path.write_text(config_content)
    click.echo(f"Created {config_path}")

    if profile:
        click.echo(f"Profile: {profile} — {_PROFILES[profile]['description']}")
    elif detector_names:
        click.echo(f"Enabled {len(detector_names)} detectors: {', '.join(detector_names)}")
    else:
        click.echo("Default: all detectors enabled")

    # Create .sentinel directory
    sentinel_dir = repo / ".sentinel"
    sentinel_dir.mkdir(exist_ok=True)

    # Add .sentinel to .gitignore if not already there
    gitignore = repo / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        lines = [line.strip() for line in content.splitlines()]
        if ".sentinel/" not in lines and ".sentinel" not in lines:
            gitignore.write_text(content + "\n# Sentinel data directory\n.sentinel/\n")
            click.echo("Added .sentinel/ to .gitignore")
    else:
        gitignore.write_text("# Sentinel data directory\n.sentinel/\n")
        click.echo("Created .gitignore with .sentinel/")

    click.echo("Done. Run 'sentinel scan .' to scan this repo.")


_TOOL_CHECKS: list[tuple[str, list[str], str]] = [
    ("git", ["git", "--version"], "Required — version control integration"),
    ("ruff", ["ruff", "--version"], "Python linter (lint-runner detector)"),
    ("pip-audit", ["pip-audit", "--version"], "Python dependency audit (dep-audit detector)"),
    ("eslint", ["eslint", "--version"], "JS/TS linter (eslint-runner detector)"),
    ("biome", ["biome", "--version"], "JS/TS linter — faster alternative to ESLint"),
    ("golangci-lint", ["golangci-lint", "--version"], "Go linter (go-linter detector)"),
    ("cargo", ["cargo", "--version"], "Rust toolchain (rust-clippy detector)"),
]


@main.command()
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def doctor(output_json: bool) -> None:
    """Check system dependencies and report what's available.

    Verifies that external tools used by detectors are installed
    and accessible. Also checks Ollama connectivity.
    """
    import shutil
    import subprocess as sp

    results: list[dict[str, str]] = []

    for name, cmd, description in _TOOL_CHECKS:
        if shutil.which(cmd[0]):
            try:
                out = sp.run(cmd, capture_output=True, text=True, timeout=5)
                version = out.stdout.strip().split("\n")[0] if out.stdout else "installed"
                results.append({"tool": name, "status": "ok", "version": version, "description": description})
            except (sp.TimeoutExpired, OSError):
                results.append({"tool": name, "status": "ok", "version": "installed", "description": description})
        else:
            results.append({"tool": name, "status": "missing", "version": "", "description": description})

    # Check Ollama (as default provider)
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in resp.json().get("models", [])]
        results.append({
            "tool": "ollama",
            "status": "ok",
            "version": f"{len(models)} model(s): {', '.join(models[:5])}",
            "description": "Local LLM provider (default)",
        })
    except Exception:
        results.append({
            "tool": "ollama",
            "status": "missing",
            "version": "",
            "description": "Local LLM provider (default) — optional if using openai provider",
        })

    # Check optional Python packages
    for pkg, desc in [("starlette", "Web UI (sentinel serve)"), ("jinja2", "Web UI templates")]:
        try:
            __import__(pkg)
            results.append({"tool": pkg, "status": "ok", "version": "installed", "description": desc})
        except ImportError:
            results.append({"tool": pkg, "status": "missing", "version": "", "description": desc})

    if output_json:
        click.echo(json.dumps({"checks": results}, indent=2))
    else:
        click.echo("Sentinel Doctor\n")
        for r in results:
            icon = "✓" if r["status"] == "ok" else "✗"
            version_str = f" ({r['version']})" if r["version"] else ""
            click.echo(f"  {icon} {r['tool']:20s}{version_str}")
            if r["status"] == "missing":
                click.echo(f"    └─ {r['description']}")
        ok = sum(1 for r in results if r["status"] == "ok")
        click.echo(f"\n{ok}/{len(results)} checks passed")


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--model", default=None, help="Model name (recorded in results)")
@click.option("--provider", "provider_name", default=None, help="Provider: ollama, openai, azure")
@click.option("--api-base", default=None, help="API base URL for openai/azure provider")
@click.option("--skip-judge", is_flag=True, help="Skip LLM-assisted detectors (deterministic only)")
@click.option("--capability", default=None, help="Model capability tier: none, basic, standard, advanced")
@click.option("--ground-truth", default=None, type=click.Path(), help="Path to ground-truth.toml for eval")
@click.option("--output-dir", default="benchmarks", help="Directory to save results (default: benchmarks/)")
@click.option("--detectors", "detector_names", default=None, help="Comma-separated list of detectors")
@click.option("--skip-detectors", "skip_detector_names", default=None, help="Comma-separated list to skip")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
@click.option("--compare", multiple=True, type=click.Path(exists=True), help="TOML files to compare (repeatable)")
def benchmark(
    repo_path: str,
    model: str | None,
    provider_name: str | None,
    api_base: str | None,
    skip_judge: bool,
    capability: str | None,
    ground_truth: str | None,
    output_dir: str,
    detector_names: str | None,
    skip_detector_names: str | None,
    output_json: bool,
    compare: tuple[str, ...],
) -> None:
    """Benchmark detectors against a repository with timing and stats.

    Results are saved to TOML files in --output-dir for tracking over time.
    Use --compare to compare multiple saved benchmarks.
    """
    # Compare mode
    if compare:
        from sentinel.core.benchmark import compare_benchmarks
        report = compare_benchmarks(list(compare))
        click.echo(report)
        return

    from sentinel.config import load_config
    from sentinel.core.benchmark import run_benchmark, save_benchmark

    repo = Path(repo_path).resolve()
    config = load_config(repo)

    # Apply overrides
    if provider_name:
        config.provider = provider_name
    if model:
        config.model = model
    if api_base:
        config.api_base = api_base
    if capability:
        config.model_capability = capability

    # Create provider if not skip_judge
    provider = None
    if not skip_judge:
        try:
            from sentinel.core.provider import create_provider
            provider = create_provider(config)
        except ValueError as exc:
            logging.getLogger(__name__).warning(
                "Could not create provider: %s — running without LLM", exc,
            )

    # Parse detector filters
    enabled = [d.strip() for d in detector_names.split(",") if d.strip()] if detector_names else None
    disabled = [d.strip() for d in skip_detector_names.split(",") if d.strip()] if skip_detector_names else None

    # Auto-detect ground truth
    if ground_truth is None:
        auto_gt = repo / "ground-truth.toml"
        if auto_gt.exists():
            ground_truth = str(auto_gt)

    click.echo(f"Benchmarking {repo} with {config.provider}/{config.model}...")

    result = run_benchmark(
        str(repo),
        provider=provider,
        skip_judge=skip_judge,
        model=config.model,
        provider_name=config.provider,
        model_capability=config.model_capability,
        num_ctx=config.num_ctx,
        enabled_detectors=enabled,
        disabled_detectors=disabled,
        detectors_dir=config.detectors_dir,
        ground_truth_path=ground_truth,
    )

    # Save results
    saved_path = save_benchmark(result, output_dir)

    if output_json:
        click.echo(json.dumps({
            "benchmark": {
                "repo_path": result.repo_path,
                "model": result.model,
                "provider": result.provider,
                "total_findings": result.total_findings,
                "total_duration_ms": result.total_duration_ms,
                "detector_count": result.detector_count,
                "saved_to": saved_path,
            },
            "detectors": [
                {"name": d.name, "findings": d.finding_count, "duration_ms": d.duration_ms}
                for d in result.detectors
            ],
            "eval": result.eval_result,
        }, indent=2))
    else:
        click.echo(f"\nResults ({result.total_duration_ms:.0f}ms total):")
        click.echo(f"  Model: {result.model} ({result.provider})")
        click.echo(f"  Detectors: {result.detector_count}")
        click.echo(f"  Findings: {result.total_findings}")
        click.echo("")
        click.echo("  Per-detector:")
        for d in sorted(result.detectors, key=lambda x: -x.finding_count):
            status = f"{d.finding_count} findings" if d.finding_count >= 0 else "FAILED"
            click.echo(f"    {d.name:25s} {status:>15s} ({d.duration_ms:.0f}ms)")

        if result.eval_result:
            click.echo("")
            click.echo("  Eval (ground truth):")
            click.echo(f"    Precision: {result.eval_result['precision']:.0%}")
            click.echo(f"    Recall:    {result.eval_result['recall']:.0%}")
            click.echo(f"    TPs: {result.eval_result['true_positives']}, "
                        f"FPs: {result.eval_result['false_positives_found']}, "
                        f"Missing: {len(result.eval_result['missing'])}")

        click.echo(f"\nSaved to: {saved_path}")


@main.command()
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--older-than", "retention_days", default=90, type=int,
              help="Delete data older than N days (default: 90)")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def prune(repo: str, db: str | None, retention_days: int, output_json: bool) -> None:
    """Remove old scan data to manage database size (TD-020).

    Deletes runs, findings, LLM logs, and persistence entries older
    than --older-than days. Suppressions are preserved.
    """
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.findings import prune_old_data

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        deleted = prune_old_data(conn, retention_days=retention_days)
        total = sum(deleted.values())

        if output_json:
            click.echo(json.dumps({"deleted": deleted, "total": total, "retention_days": retention_days}))
        else:
            if total == 0:
                click.echo(f"Nothing to prune (retention: {retention_days} days).")
            else:
                click.echo(f"Pruned data older than {retention_days} days:")
                for table, count in sorted(deleted.items()):
                    if count > 0:
                        click.echo(f"  {table}: {count} rows deleted")
                click.echo(f"  Total: {total} rows deleted")
    finally:
        conn.close()

