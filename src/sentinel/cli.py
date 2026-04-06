"""CLI entry point for Sentinel."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import click

from sentinel import __version__


@click.group()
@click.version_option(version=__version__, prog_name="sentinel")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
def main(verbose: bool) -> None:
    """Local Repo Sentinel — overnight code health monitoring."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--model", default=None, help="Ollama model name")
@click.option("--ollama-url", default=None, help="Ollama API URL")
@click.option("--output", "-o", default=None, help="Report output path")
@click.option("--skip-judge", is_flag=True, help="Skip LLM judge (use raw findings)")
@click.option("--db", default=None, help="Database path")
@click.option(
    "--incremental", is_flag=True,
    help="Only scan files changed since the last completed run",
)
@click.option("--embed-model", default=None, help="Ollama embedding model (enables semantic context)")
@click.option("--target", "-t", multiple=True, help="Scan only specific paths (repeatable)")
def scan(
    repo_path: str,
    model: str | None,
    ollama_url: str | None,
    output: str | None,
    skip_judge: bool,
    db: str | None,
    incremental: bool,
    embed_model: str | None,
    target: tuple[str, ...],
) -> None:
    """Run detectors against a repository and generate a morning report."""
    from sentinel.config import load_config
    from sentinel.core.runner import prepare_incremental, run_scan
    from sentinel.models import ScopeType
    from sentinel.store.db import get_connection

    repo = Path(repo_path).resolve()
    config = load_config(repo)

    # CLI flags override config file
    if model:
        config.model = model
    if ollama_url:
        config.ollama_url = ollama_url
    if skip_judge:
        config.skip_judge = True
    if embed_model:
        config.embed_model = embed_model

    db_path = db or str(repo / config.db_path)
    conn = get_connection(db_path)

    try:
        # If user gave -o, use it; otherwise let runner generate report-{run.id}.md
        output_path = output or None

        scope_type = None
        changed_files = None
        target_paths = list(target) if target else None

        if incremental and target_paths:
            click.echo("Cannot use --incremental and --target together.", err=True)
            raise SystemExit(1)

        if target_paths:
            scope_type = ScopeType.TARGETED
        elif incremental:
            scope_type, changed_files = prepare_incremental(str(repo), conn)
            if scope_type == ScopeType.INCREMENTAL and changed_files is not None and len(changed_files) == 0:
                click.echo("No changes since last run — nothing to scan.")
                return

        kwargs: dict[str, Any] = dict(
            model=config.model,
            ollama_url=config.ollama_url,
            skip_judge=config.skip_judge,
            embed_model=config.embed_model,
            embed_chunk_size=config.embed_chunk_size,
            embed_chunk_overlap=config.embed_chunk_overlap,
            detectors_dir=config.detectors_dir,
        )
        if output_path is not None:
            kwargs["output_path"] = output_path
        if scope_type is not None:
            kwargs["scope"] = scope_type
        if changed_files is not None:
            kwargs["changed_files"] = changed_files
        if target_paths is not None:
            kwargs["target_paths"] = target_paths

        run, findings, _report = run_scan(str(repo), conn, **kwargs)
        # Derive actual report path
        actual_path = output_path or str(repo / config.output_dir / f"report-{run.id}.md")
        click.echo(f"Scan complete: {len(findings)} findings in run #{run.id}")
        if incremental and changed_files:
            click.echo(f"Incremental: {len(changed_files)} files changed since last run")
        click.echo(f"Report: {actual_path}")
    finally:
        conn.close()


@main.command()
@click.argument("finding_id", type=int)
@click.option("--reason", "-r", default=None, help="Reason for suppression")
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
def suppress(finding_id: int, reason: str | None, repo: str, db: str | None) -> None:
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
            click.echo(f"Finding #{finding_id} not found.", err=True)
            raise SystemExit(1)

        suppress_finding(conn, finding.fingerprint, reason=reason)
        click.echo(f"Suppressed finding #{finding_id}: {finding.title}")
    finally:
        conn.close()


@main.command()
@click.argument("finding_id", type=int)
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
def approve(finding_id: int, repo: str, db: str | None) -> None:
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
            click.echo(f"Finding #{finding_id} not found.", err=True)
            raise SystemExit(1)

        update_finding_status(conn, finding_id, FindingStatus.APPROVED)
        click.echo(f"Approved finding #{finding_id}: {finding.title}")
        click.echo("Run 'sentinel create-issues' to create GitHub issues from approved findings.")
    finally:
        conn.close()


@main.command()
@click.argument("finding_id", type=int)
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
def show(finding_id: int, repo: str, db: str | None) -> None:
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
            click.echo(f"Finding #{finding_id} not found.", err=True)
            raise SystemExit(1)

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
def create_issues_cmd(
    repo: str,
    db: str | None,
    owner: str | None,
    github_repo: str | None,
    token: str | None,
    dry_run: bool,
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
            click.echo("No approved findings to create issues for.")
            return

        click.echo(f"Found {len(approved)} approved finding(s)")

        if dry_run and gh is None:
            # dry run without GitHub config — just show what would be created
            for _db_id, finding in approved:
                click.echo(f"  [DRY RUN] Would create: [Sentinel] {finding.title}")
            return

        assert gh is not None  # non-dry-run checked above; dry-run returned above
        results = create_issues(conn, gh, dry_run=dry_run)

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
@click.option("--repo", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--db", default=None, help="Database path")
@click.option("--limit", "-n", default=20, help="Number of runs to show")
def history(repo: str, db: str | None, limit: int) -> None:
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
            click.echo("No runs found.")
            return

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
              help="Ollama embedding model (default: from config or nomic-embed-text)")
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

    Chunks repo files and embeds them via Ollama for use during scan.
    Only re-embeds files that have changed since the last index build.
    """
    from sentinel.config import load_config
    from sentinel.core.indexer import build_index
    from sentinel.store.db import get_connection
    from sentinel.store.embeddings import chunk_count, clear_all_chunks

    repo = Path(repo_path).resolve()
    config = load_config(repo)

    if ollama_url:
        config.ollama_url = ollama_url

    # Resolve embed model: CLI flag > config > default
    resolved_model = embed_model or config.embed_model or "nomic-embed-text"

    db_path = db or str(repo / config.db_path)
    conn = get_connection(db_path)

    try:
        if clear:
            cleared = clear_all_chunks(conn)
            click.echo(f"Cleared {cleared} existing chunks")

        click.echo(f"Building embedding index with model '{resolved_model}'...")
        stats = build_index(
            str(repo), conn, resolved_model,
            ollama_url=config.ollama_url,
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
def eval(
    repo_path: str,
    ground_truth: str | None,
    db: str | None,
) -> None:
    """Evaluate detector precision/recall against annotated ground truth.

    Runs all detectors on REPO_PATH and compares results to GROUND_TRUTH.
    Prints precision, recall, and details of mismatches.
    """
    from sentinel.core.eval import evaluate, load_ground_truth
    from sentinel.core.runner import run_scan
    from sentinel.store.db import get_connection

    repo = Path(repo_path).resolve()

    # Find ground truth file
    gt_path = Path(ground_truth) if ground_truth else repo / "ground-truth.toml"
    if not gt_path.exists():
        click.echo(f"Ground truth file not found: {gt_path}", err=True)
        click.echo("Create a ground-truth.toml file or use --ground-truth to specify one.", err=True)
        raise SystemExit(1)

    gt = load_ground_truth(gt_path)

    # Run scan (skip LLM judge for deterministic evaluation)
    conn = get_connection(db or ":memory:")
    try:
        _, findings, _ = run_scan(
            str(repo), conn, skip_judge=True, output_path="/dev/null",
        )
    finally:
        conn.close()

    result = evaluate(findings, gt)

    # Print results
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

    # Exit code: 0 if precision >= 70% and recall >= 90%
    if result.precision >= 0.70 and result.recall >= 0.90:
        click.echo("")
        click.echo("✓ PASS — meets ADR-008 targets (precision ≥70%, recall ≥90%)")
    else:
        click.echo("")
        click.echo("✗ FAIL — below ADR-008 targets")
        raise SystemExit(1)


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


if __name__ == "__main__":
    main()
