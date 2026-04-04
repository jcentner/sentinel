"""CLI entry point for Sentinel."""

import click

from sentinel import __version__


@click.group()
@click.version_option(version=__version__, prog_name="sentinel")
def main() -> None:
    """Local Repo Sentinel — overnight code health monitoring."""


@main.command()
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
def scan(repo_path: str) -> None:
    """Run detectors against a repository and generate a morning report."""
    click.echo(f"Scanning {repo_path}...")
    # Pipeline will be wired in Slice 12


if __name__ == "__main__":
    main()
