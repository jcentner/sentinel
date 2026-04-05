"""CLI entry point for Sentinel."""

from __future__ import annotations

import logging
from pathlib import Path

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
def scan(
    repo_path: str,
    model: str | None,
    ollama_url: str | None,
    output: str | None,
    skip_judge: bool,
    db: str | None,
) -> None:
    """Run detectors against a repository and generate a morning report."""
    from sentinel.config import load_config
    from sentinel.core.runner import run_scan
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

    db_path = db or str(repo / config.db_path)
    conn = get_connection(db_path)

    output_path = output or str(repo / config.output_dir / "report.md")

    try:
        run, findings, _report = run_scan(
            str(repo),
            conn,
            model=config.model,
            ollama_url=config.ollama_url,
            output_path=output_path,
            skip_judge=config.skip_judge,
        )
        click.echo(f"Scan complete: {len(findings)} findings in run #{run.id}")
        click.echo(f"Report: {output_path}")
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


if __name__ == "__main__":
    main()
