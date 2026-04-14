"""CLI entry point for Sentinel."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from sentinel import __version__

if TYPE_CHECKING:
    from sentinel.config import SentinelConfig
    from sentinel.core.provider import ModelProvider


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
@click.option("--skip-llm", is_flag=True, help="Skip LLM-assisted detectors (semantic-drift, test-coherence)")
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
    skip_llm: bool,
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
                         capability=capability,
                         skip_llm=skip_llm)

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
    skip_llm: bool = False,
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
    if skip_llm:
        config.skip_llm = True
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

    # Create the model provider from config (None if both judge and LLM detectors skipped)
    provider = None
    if not (config.skip_judge and config.skip_llm):
        try:
            provider = create_provider(config)
        except ValueError as exc:
            logging.getLogger(__name__).warning(
                "Could not create model provider: %s — running without LLM", exc,
            )

    kwargs: dict[str, Any] = dict(
        provider=provider,
        skip_judge=config.skip_judge,
        skip_llm=config.skip_llm,
        embed_model=config.embed_model,
        embed_chunk_size=config.embed_chunk_size,
        embed_chunk_overlap=config.embed_chunk_overlap,
        detectors_dir=config.detectors_dir,
        output_dir=config.output_dir,
        num_ctx=config.num_ctx,
        model_capability=config.model_capability,
        min_confidence=config.min_confidence,
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


@main.command(name="bulk-approve")
@click.option("--run", "run_id", type=int, default=None, help="Approve all findings in this run")
@click.option("--ids", default=None, help="Comma-separated list of finding IDs")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def bulk_approve(
    run_id: int | None,
    ids: str | None,
    repo: str,
    db: str | None,
    output_json: bool,
) -> None:
    """Approve multiple findings at once.

    Use --run to approve all findings in a run, or --ids for specific IDs.
    """
    from sentinel.config import load_config
    from sentinel.models import FindingStatus
    from sentinel.store.db import get_connection
    from sentinel.store.findings import (
        get_finding_by_id,
        get_findings_by_run,
        update_finding_status,
    )

    if not run_id and not ids:
        msg = "Specify --run <run_id> or --ids <id1,id2,...>"
        if output_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(msg, err=True)
        raise SystemExit(1)

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        finding_ids: list[int] = []
        if run_id:
            findings = get_findings_by_run(conn, run_id)
            finding_ids = [f.id for f in findings if f.id is not None]
        elif ids:
            finding_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]

        count = 0
        for fid in finding_ids:
            finding = get_finding_by_id(conn, fid)
            if finding is not None:
                update_finding_status(conn, fid, FindingStatus.APPROVED)
                count += 1

        if output_json:
            click.echo(json.dumps({"approved": count, "total": len(finding_ids)}))
        else:
            click.echo(f"Approved {count} finding(s).")
    finally:
        conn.close()


@main.command(name="bulk-suppress")
@click.option("--run", "run_id", type=int, default=None, help="Suppress all findings in this run")
@click.option("--ids", default=None, help="Comma-separated list of finding IDs")
@click.option("--reason", default=None, help="Reason for suppression")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def bulk_suppress(
    run_id: int | None,
    ids: str | None,
    reason: str | None,
    repo: str,
    db: str | None,
    output_json: bool,
) -> None:
    """Suppress multiple findings at once.

    Use --run to suppress all findings in a run, or --ids for specific IDs.
    """
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.findings import get_finding_by_id, get_findings_by_run, suppress_finding

    if not run_id and not ids:
        msg = "Specify --run <run_id> or --ids <id1,id2,...>"
        if output_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(msg, err=True)
        raise SystemExit(1)

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        finding_ids: list[int] = []
        if run_id:
            findings = get_findings_by_run(conn, run_id)
            finding_ids = [f.id for f in findings if f.id is not None]
        elif ids:
            finding_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]

        count = 0
        for fid in finding_ids:
            finding = get_finding_by_id(conn, fid)
            if finding is not None and finding.fingerprint:
                suppress_finding(conn, finding.fingerprint, reason=reason)
                count += 1

        if output_json:
            click.echo(json.dumps({"suppressed": count, "total": len(finding_ids)}))
        else:
            click.echo(f"Suppressed {count} finding(s).")
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
        msg = (
            "GitHub config required. Set --owner, --github-repo, --token "
            "or SENTINEL_GITHUB_OWNER, SENTINEL_GITHUB_REPO, SENTINEL_GITHUB_TOKEN env vars."
        )
        if output_json:
            click.echo(json.dumps({"error": msg}))
        else:
            click.echo(msg, err=True)
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

        assert run_id is not None  # guaranteed by get_run_history check above
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
@click.argument("run_id", type=int)
@click.argument("base_run_id", type=int)
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--json-output", "output_json", is_flag=True, help="Output as JSON")
def compare(
    run_id: int,
    base_run_id: int,
    repo: str,
    db: str | None,
    output_json: bool,
) -> None:
    """Compare findings between two scan runs.

    Shows new, resolved, and persistent findings between BASE_RUN_ID and RUN_ID.
    BASE_RUN_ID is the earlier (baseline) run, RUN_ID is the later run.
    """
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.findings import compare_runs
    from sentinel.store.runs import get_run_by_id

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        base_run = get_run_by_id(conn, base_run_id)
        target_run = get_run_by_id(conn, run_id)
        if not base_run:
            if output_json:
                click.echo(json.dumps({"error": f"Base run #{base_run_id} not found"}))
            else:
                click.echo(f"Base run #{base_run_id} not found.", err=True)
            raise SystemExit(1)
        if not target_run:
            if output_json:
                click.echo(json.dumps({"error": f"Run #{run_id} not found"}))
            else:
                click.echo(f"Run #{run_id} not found.", err=True)
            raise SystemExit(1)

        new, resolved, persistent = compare_runs(conn, base_run_id, run_id)

        if output_json:
            click.echo(json.dumps({
                "base_run_id": base_run_id,
                "run_id": run_id,
                "new": [f.to_dict() for f in new],
                "resolved": [f.to_dict() for f in resolved],
                "persistent": [f.to_dict() for f in persistent],
                "summary": {
                    "new_count": len(new),
                    "resolved_count": len(resolved),
                    "persistent_count": len(persistent),
                    "net_change": len(new) - len(resolved),
                },
            }, indent=2))
        else:
            click.echo(f"Comparing run #{base_run_id} → #{run_id}\n")
            click.echo(f"  New:        {len(new):>4}")
            click.echo(f"  Resolved:   {len(resolved):>4}")
            click.echo(f"  Persistent: {len(persistent):>4}")
            net = len(new) - len(resolved)
            sign = "+" if net > 0 else ""
            click.echo(f"  Net change: {sign}{net:>3}\n")

            if new:
                click.echo("New findings:")
                click.echo(f"  {'ID':>5}  {'Severity':<9}  {'Detector':<20}  {'Title'}")
                click.echo("  " + "-" * 70)
                for f in new:
                    click.echo(
                        f"  {f.id:>5}  {f.severity.value:<9}  {f.detector:<20}  {f.title[:35]}"
                    )
                click.echo()

            if resolved:
                click.echo("Resolved findings:")
                click.echo(f"  {'ID':>5}  {'Severity':<9}  {'Detector':<20}  {'Title'}")
                click.echo("  " + "-" * 70)
                for f in resolved:
                    click.echo(
                        f"  {f.id:>5}  {f.severity.value:<9}  {f.detector:<20}  {f.title[:35]}"
                    )
                click.echo()
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
@click.option("--full-pipeline", is_flag=True, default=False,
              help="Run with LLM judge enabled (requires --replay-file or a configured provider)")
@click.option("--replay-file", default=None, type=click.Path(exists=True),
              help="Path to recorded judge responses for deterministic replay")
@click.option("--record-responses", default=None, type=click.Path(),
              help="Record judge responses to this file for later replay")
def eval(
    repo_path: str,
    ground_truth: str | None,
    db: str | None,
    output_json: bool,
    full_pipeline: bool,
    replay_file: str | None,
    record_responses: str | None,
) -> None:
    """Evaluate detector precision/recall against annotated ground truth.

    Runs all detectors on REPO_PATH and compares results to GROUND_TRUTH.
    Prints precision, recall, and details of mismatches.

    With --full-pipeline, runs the LLM judge on findings before evaluation.
    Use --replay-file to provide pre-recorded judge responses (for CI).
    Use --record-responses to capture judge responses for later replay.
    """
    import os

    from sentinel.config import load_config
    from sentinel.core.eval import evaluate, load_ground_truth
    from sentinel.core.runner import run_scan
    from sentinel.store.db import get_connection
    from sentinel.store.eval_store import save_eval_result

    repo = Path(repo_path).resolve()

    # Find ground truth file
    gt_path = Path(ground_truth) if ground_truth else repo / "ground-truth.toml"
    if not gt_path.exists():
        if output_json:
            click.echo(json.dumps({"error": f"Ground truth file not found: {gt_path}"}))
        else:
            click.echo(f"Ground truth file not found: {gt_path}", err=True)
            click.echo("Create a ground-truth.toml file or use --ground-truth to specify one.", err=True)
        raise SystemExit(1)

    gt = load_ground_truth(gt_path)

    # Resolve provider for full-pipeline mode
    provider: ModelProvider | None = None
    recording_provider: ModelProvider | None = None
    if full_pipeline:
        if replay_file:
            from sentinel.core.providers.replay import ReplayProvider
            provider = ReplayProvider.from_file(replay_file)
        else:
            from sentinel.core.provider import create_provider
            config = load_config(repo)
            provider = create_provider(config)
            if not provider.check_health():
                if output_json:
                    click.echo(json.dumps({"error": "Full-pipeline eval requires a healthy model provider"}))
                else:
                    click.echo("Full-pipeline eval requires a healthy model provider.", err=True)
                    click.echo("Use --replay-file for offline evaluation.", err=True)
                raise SystemExit(1)

        if record_responses and provider is not None:
            from sentinel.core.providers.replay import RecordingProvider
            recording_provider = RecordingProvider(provider)
            provider = recording_provider

    # Use the real DB if specified, otherwise default to the repo's configured DB
    # so eval results persist across runs
    if db:
        db_actual = db
    else:
        config = load_config(repo)
        db_actual = str(repo / config.db_path)

    conn = get_connection(db_actual)
    try:
        skip_judge = not full_pipeline
        _, findings, _ = run_scan(
            str(repo), conn,
            skip_judge=skip_judge,
            provider=provider,
            output_path=os.devnull,
        )

        result = evaluate(
            findings, gt,
            include_judge_metrics=full_pipeline,
        )
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

    # Save recordings if requested
    if recording_provider is not None and record_responses:
        from sentinel.core.providers.replay import RecordingProvider
        assert isinstance(recording_provider, RecordingProvider)
        recording_provider.save(record_responses)
        if not output_json:
            click.echo(f"\nRecorded {len(recording_provider.recordings)} responses to {record_responses}")

    if output_json:
        data = result.to_dict()
        data["repo"] = str(repo)
        data["passed"] = passed
        if full_pipeline and replay_file and provider is not None:
            from sentinel.core.providers.replay import ReplayProvider
            if isinstance(provider, ReplayProvider):
                data["replay_match_rate"] = provider.match_rate
                data["replay_hits"] = provider.hits
                data["replay_misses"] = provider.misses
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo("")
        click.echo("═══ Sentinel Evaluation ═══")
        click.echo(f"Repo:     {repo}")
        if full_pipeline:
            click.echo(f"Mode:     full-pipeline (judge {'replay' if replay_file else 'live'})")
        click.echo(f"Findings: {result.total_findings}")
        click.echo(f"TP:       {result.true_positives}")
        click.echo(f"Missing:  {len(result.missing)}")
        click.echo(f"FP found: {result.false_positives_found}")
        click.echo("")
        click.echo(f"Precision: {result.precision:.0%}")
        click.echo(f"Recall:    {result.recall:.0%}")

        # Per-detector breakdown
        if result.per_detector:
            click.echo("")
            click.echo("Per-detector breakdown:")
            click.echo(f"  {'Detector':<20} {'Findings':>8} {'TP':>4} {'Expected':>8} {'Prec':>6} {'Recall':>6}")
            click.echo("  " + "-" * 60)
            for det_r in result.per_detector.values():
                click.echo(
                    f"  {det_r.detector:<20} {det_r.total_findings:>8} "
                    f"{det_r.true_positives:>4} {det_r.expected:>8} "
                    f"{det_r.precision:>5.0%} {det_r.recall:>5.0%}"
                )

        # Judge metrics
        if result.judge is not None and result.judge.total_judged > 0:
            j = result.judge
            click.echo("")
            click.echo("Judge metrics:")
            click.echo(f"  Judged:          {j.total_judged}")
            click.echo(f"  Confirmed:       {j.confirmed} ({j.confirmation_rate:.0%})")
            click.echo(f"  Rejected:        {j.rejected} ({j.rejection_rate:.0%})")
            click.echo(f"  Inconclusive:    {j.inconclusive}")
            if j.expected_tp_rejected:
                click.echo(f"  ⚠ TPs rejected:  {j.expected_tp_rejected}")

        # Replay stats
        if full_pipeline and replay_file and provider is not None:
            from sentinel.core.providers.replay import ReplayProvider
            if isinstance(provider, ReplayProvider):
                click.echo("")
                click.echo(f"Replay: {provider.hits} hits, {provider.misses} misses "
                           f"({provider.match_rate:.0%} match rate)")

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


@main.command("llm-log")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--run-id", default=None, type=int, help="Filter by run ID")
@click.option("--detector", default="", help="Filter by detector name")
@click.option("--model", default="", help="Filter by model name")
@click.option("--verdict", default="", help="Filter by verdict")
@click.option("--limit", "-n", default=50, help="Number of entries to show")
@click.option("--stats", is_flag=True, help="Show aggregate statistics instead of entries")
@click.option("--json-output", "output_json", is_flag=True, help="Output as JSON")
def llm_log(
    repo: str,
    db: str | None,
    run_id: int | None,
    detector: str,
    model: str,
    verdict: str,
    limit: int,
    stats: bool,
    output_json: bool,
) -> None:
    """Browse and filter LLM interaction log entries.

    Shows prompts, responses, verdicts, and timing for all LLM calls
    made during scans. Use --stats for aggregate statistics.

    Examples:
        sentinel llm-log --stats
        sentinel llm-log --detector test-coherence --verdict confirmed
        sentinel llm-log --model gpt-5.4-nano --limit 10 --json-output
    """
    from sentinel.config import load_config
    from sentinel.store.db import get_connection
    from sentinel.store.llm_log import (
        get_llm_log_entries,
        get_llm_log_stats,
        get_model_speed_stats,
    )

    repo_path = Path(repo).resolve()
    config = load_config(repo_path)
    db_path = db or str(repo_path / config.db_path)

    conn = get_connection(db_path)
    try:
        if stats:
            summary = get_llm_log_stats(conn, run_id=run_id)
            speed = get_model_speed_stats(conn)
            if output_json:
                click.echo(json.dumps({"stats": summary, "model_speed": speed}, indent=2))
            else:
                if not summary or not summary.get("total_calls"):
                    click.echo("No LLM log entries found.")
                    return
                click.echo("LLM Log Statistics")
                click.echo("=" * 40)
                click.echo(f"  Total calls:     {summary['total_calls']}")
                click.echo(f"  Judge calls:     {summary.get('judge_calls', 0)}")
                click.echo(f"  Doc-code calls:  {summary.get('doc_code_calls', 0)}")
                click.echo(f"  Confirmed:       {summary.get('confirmed', 0)}")
                click.echo(f"  Likely FP:       {summary.get('likely_fp', 0)}")
                click.echo(f"  Drift detected:  {summary.get('drift_detected', 0)}")
                click.echo(f"  Accurate:        {summary.get('accurate', 0)}")
                click.echo(f"  Errors:          {summary.get('errors', 0)}")
                click.echo(f"  No-parse:        {summary.get('no_parse', 0)}")
                total_ms = summary.get("total_generation_ms") or 0
                click.echo(f"  Total time:      {total_ms / 1000:.1f}s")
                click.echo(f"  Total tokens:    {summary.get('total_tokens', 0)}")

                if speed:
                    click.echo("\nModel Speed")
                    click.echo("-" * 40)
                    for m, s in speed.items():
                        click.echo(f"  {m}: {s['calls']} calls, {s['avg_tok_s']} tok/s")
            return

        entries, total = get_llm_log_entries(
            conn,
            detector=detector,
            model=model,
            verdict=verdict,
            run_id=run_id,
            limit=limit,
        )

        if not entries:
            if output_json:
                click.echo(json.dumps([]))
            else:
                click.echo("No LLM log entries found.")
            return

        if output_json:
            click.echo(json.dumps(entries, indent=2, default=str))
        else:
            click.echo(f"Showing {len(entries)} of {total} entries")
            click.echo(
                f"{'ID':>5}  {'Run':>4}  {'Purpose':>12}  {'Detector':>22}  "
                f"{'Model':>16}  {'Verdict':>18}  {'ms':>7}  {'Tokens':>6}"
            )
            click.echo("-" * 100)
            for e in entries:
                run_str = str(e.get('run_id') or '-')
                ms_val = e.get('generation_ms') or 0
                tok_val = e.get('tokens_generated') or 0
                click.echo(
                    f"{e.get('id', ''):>5}  "
                    f"{run_str:>4}  "
                    f"{e.get('purpose', ''):>12}  "
                    f"{(e.get('detector') or ''):>22}  "
                    f"{(e.get('model') or ''):>16}  "
                    f"{(e.get('verdict') or ''):>18}  "
                    f"{ms_val:>7.0f}  "
                    f"{tok_val:>6}"
                )
    finally:
        conn.close()


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--host", default="127.0.0.1", help="Bind address (default: localhost only)")
@click.option("--port", default=8888, type=int, help="Port number")
@click.option("--db", default=None, help="Database path")
@click.option("--open/--no-open", "open_browser", default=True, help="Auto-open browser (default: open)")
def serve(
    repo_path: str,
    host: str,
    port: int,
    db: str | None,
    open_browser: bool,
) -> None:
    """Start the local web UI for reviewing scan results.

    Launches a browser-based interface on localhost for browsing
    runs, reviewing findings, and approving/suppressing issues.
    Auto-opens the browser by default (use --no-open to disable).
    Requires the [web] optional dependency group.
    """
    try:
        import uvicorn
    except ImportError:
        click.echo(
            'Web UI dependencies not installed. Run: pip install "repo-sentinel[web]"',
            err=True,
        )
        raise SystemExit(1) from None

    from sentinel.config import load_config
    from sentinel.web.app import create_app

    repo = Path(repo_path).resolve()
    config = load_config(repo)
    db_path = db or str(repo / config.db_path)

    app = create_app(repo_path=str(repo), db_path=db_path)
    url = f"http://{host}:{port}"
    click.echo(f"Sentinel web UI: {url}")

    if open_browser:
        import threading
        import webbrowser

        # Open browser after a short delay to let the server start
        timer = threading.Timer(1.0, webbrowser.open, args=[url])
        timer.daemon = True
        timer.start()
    else:
        timer = None

    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        if timer is not None:
            timer.cancel()


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
_ProfileFilter = Callable[[str], bool]


@dataclass
class _Profile:
    description: str
    model_capability: str
    skip_judge: bool
    filter: _ProfileFilter


_PROFILES: dict[str, _Profile] = {
    "minimal": _Profile(
        description="Heuristic-only detectors, no LLM required",
        model_capability="none",
        skip_judge=True,
        filter=lambda tier: tier == "none",
    ),
    "standard": _Profile(
        description="All detectors with basic LLM support",
        model_capability="basic",
        skip_judge=False,
        filter=lambda tier: True,
    ),
    "full": _Profile(
        description="All detectors with enhanced LLM analysis",
        model_capability="standard",
        skip_judge=False,
        filter=lambda tier: True,
    ),
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
        enabled = [d["name"] for d in all_detectors if p.filter(d["tier"])]
        cap = p.model_capability
        skip = p.skip_judge
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
            count = sum(1 for d in detectors if p.filter(d["tier"]))
            click.echo(f"  {name:10s}  {count:2d} detectors — {p.description}")
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
        click.echo(f"Profile: {profile} — {_PROFILES[profile].description}")
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


@main.command()
@click.option("--json-output", "output_json", is_flag=True, help="Output results as JSON")
def doctor(output_json: bool) -> None:
    """Check system dependencies, configuration, and report what's available.

    Verifies that external tools used by detectors are installed
    and accessible. Also checks Ollama connectivity and sentinel.toml validity.
    """
    from sentinel.core.doctor import run_doctor_checks

    check_results = run_doctor_checks(".")
    results = [
        {"tool": r.tool, "status": r.status, "version": r.version, "description": r.description}
        for r in check_results
    ]

    if output_json:
        click.echo(json.dumps({"checks": results}, indent=2))
    else:
        click.echo("Sentinel Doctor\n")
        for r in results:
            icon = "✓" if r["status"] == "ok" else "✗"
            version_str = f" ({r['version']})" if r["version"] else ""
            click.echo(f"  {icon} {r['tool']:20s}{version_str}")
            if r["status"] in ("missing", "error"):
                click.echo(f"    └─ {r['description']}")
        ok = sum(1 for r in results if r["status"] == "ok")
        click.echo(f"\n{ok}/{len(results)} checks passed")


@main.command()
@click.option("--detector", "-d", default=None, help="Show matrix for a specific detector")
@click.option("--model", "-m", default=None, help="Show matrix for a specific model class")
@click.option("--json-output", "output_json", is_flag=True, help="Output as JSON")
def compatibility(detector: str | None, model: str | None, output_json: bool) -> None:
    """Show model-detector compatibility matrix.

    Displays empirical quality ratings for each model class and detector
    combination, based on real-world benchmarks. Use this to choose models
    that work well with the detectors you need.

    \b
    Examples:
      sentinel compatibility                  # Full matrix
      sentinel compatibility -d test-coherence  # One detector
      sentinel compatibility -m 4b-local      # One model class
      sentinel compatibility --json-output    # Machine-readable
    """
    from sentinel.core.compatibility import (
        DETECTOR_INFO,
        MODEL_CLASSES,
        QualityRating,
        build_summary_table,
        get_detector_recommendation,
        get_matrix_for_detector,
        get_matrix_for_model,
    )

    if output_json:
        rows = build_summary_table()
        if detector:
            rows = [r for r in rows if r["detector"] == detector]
        if model:
            rows = [
                {k: v for k, v in r.items() if k in ("detector", "tier", "capability", "description", model)}
                for r in rows
            ]
        click.echo(json.dumps({"compatibility": rows}, indent=2))
        return

    # Determine what to show
    if detector:
        entries = get_matrix_for_detector(detector)
        if not entries:
            click.echo(f"Unknown detector: {detector}")
            click.echo(f"Available: {', '.join(DETECTOR_INFO.keys())}")
            raise SystemExit(1)
        click.echo(f"Compatibility: {detector}\n")
        for e in entries:
            _print_compat_entry(e)
        click.echo(f"\n{get_detector_recommendation(detector)}")
        return

    if model:
        entries = get_matrix_for_model(model)
        if not entries:
            click.echo(f"Unknown model class: {model}")
            click.echo(f"Available: {', '.join(m['id'] for m in MODEL_CLASSES)}")
            raise SystemExit(1)
        mc_info = next((m for m in MODEL_CLASSES if m["id"] == model), None)
        click.echo(f"Compatibility: {model}")
        if mc_info:
            click.echo(f"  Example: {mc_info['example']}\n")
        for e in entries:
            _print_compat_entry(e, show_detector=True)
        return

    # Full matrix table
    mc_ids = [m["id"] for m in MODEL_CLASSES]
    rows = build_summary_table()

    # Header
    det_width = max(len(str(r["detector"])) for r in rows) + 2
    col_width = 12
    header = f"{'Detector':<{det_width}}"
    for mc_id in mc_ids:
        header += f"{mc_id:^{col_width}}"
    click.echo(header)
    click.echo("─" * len(header))

    rating_symbols = {
        QualityRating.EXCELLENT.value: "★★★",
        QualityRating.GOOD.value: "★★ ",
        QualityRating.FAIR.value: "★  ",
        QualityRating.POOR.value: "✗  ",
        QualityRating.NA.value: "─  ",
        QualityRating.UNTESTED.value: "?  ",
    }

    for row in rows:
        det_name = str(row["detector"])
        line = f"{det_name:<{det_width}}"
        for mc_id in mc_ids:
            cell = row.get(mc_id)
            if isinstance(cell, dict):
                rating = str(cell.get("rating", "untested"))
                symbol = rating_symbols.get(rating, "?  ")
                line += f"{symbol:^{col_width}}"
            else:
                line += f"{'─':^{col_width}}"
        click.echo(line)

    click.echo()
    click.echo("Legend: ★★★ excellent  ★★ good  ★ fair  ✗ poor  ─ n/a  ? untested")
    click.echo("\nFor details: sentinel compatibility -d <detector>")


def _print_compat_entry(e: Any, show_detector: bool = False) -> None:
    """Print a single compatibility entry in human-readable form."""
    rating_colors = {
        "excellent": "green",
        "good": "blue",
        "fair": "yellow",
        "poor": "red",
    }
    color = rating_colors.get(e.rating.value)
    label = click.style(e.rating.value.upper(), fg=color, bold=color == "red")
    prefix = f"{e.detector:20s}" if show_detector else f"  {e.model_class:15s}"
    click.echo(f"{prefix} {label:20s} FP: {e.fp_rate:8s}  {e.notes}")


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--model", default=None, help="Model name (recorded in results)")
@click.option("--provider", "provider_name", default=None, help="Provider: ollama, openai, azure")
@click.option("--api-base", default=None, help="API base URL for openai/azure provider")
@click.option("--api-key-env", default=None, help="Environment variable containing the API key (e.g. OPENAI_API_KEY)")
@click.option("--skip-judge", is_flag=True, help="Skip LLM judge (use raw findings)")
@click.option("--skip-llm", "skip_llm", is_flag=True, help="Disable LLM-assisted detectors (semantic-drift, test-coherence)")
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
    api_key_env: str | None,
    skip_judge: bool,
    skip_llm: bool,
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
    if api_key_env:
        config.api_key_env = api_key_env
    if capability:
        config.model_capability = capability

    # Create provider if LLM features are needed
    provider = None
    needs_provider = not (skip_judge and skip_llm)
    if needs_provider:
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
        skip_llm=skip_llm,
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

