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


if __name__ == "__main__":
    main()
