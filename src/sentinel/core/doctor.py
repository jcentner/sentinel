"""System health checks for Sentinel doctor command."""

from __future__ import annotations

import shutil
import subprocess as sp
from dataclasses import dataclass
from pathlib import Path

_TOOL_CHECKS = [
    ("git", ["git", "--version"], "Version control (required for git-hotspots, incremental scans)"),
    ("ruff", ["ruff", "--version"], "Python linter (lint-runner detector)"),
    ("pip-audit", ["pip-audit", "--version"], "Python dependency audit (dep-audit detector)"),
    ("eslint", ["eslint", "--version"], "JS/TS linter (eslint-runner detector)"),
    ("biome", ["biome", "--version"], "JS/TS linter — faster alternative to ESLint"),
    ("golangci-lint", ["golangci-lint", "--version"], "Go linter (go-linter detector)"),
    ("cargo", ["cargo", "--version"], "Rust toolchain (rust-clippy detector)"),
]


@dataclass
class CheckResult:
    """Result of a single health check."""

    tool: str
    status: str  # "ok", "missing", "error"
    version: str
    description: str


def run_doctor_checks(repo_path: str | Path | None = None) -> list[CheckResult]:
    """Run all system health checks and return results.

    This is the shared implementation used by both the CLI ``doctor``
    command and the web UI doctor page.
    """
    results: list[CheckResult] = []

    # External tool checks
    for name, cmd, description in _TOOL_CHECKS:
        if shutil.which(cmd[0]):
            try:
                out = sp.run(cmd, capture_output=True, text=True, timeout=5)
                version = out.stdout.strip().split("\n")[0] if out.stdout else "installed"
                results.append(CheckResult(tool=name, status="ok", version=version, description=description))
            except (sp.TimeoutExpired, OSError):
                results.append(CheckResult(tool=name, status="ok", version="installed", description=description))
        else:
            results.append(CheckResult(tool=name, status="missing", version="", description=description))

    # Ollama check
    try:
        import httpx

        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in resp.json().get("models", [])]
        results.append(CheckResult(
            tool="ollama",
            status="ok",
            version=f"{len(models)} model(s): {', '.join(models[:5])}",
            description="Local LLM provider (default)",
        ))
    except Exception:
        results.append(CheckResult(
            tool="ollama",
            status="missing",
            version="",
            description="Local LLM provider (default) — optional if using openai provider",
        ))

    # Optional Python packages
    for pkg, desc in [("starlette", "Web UI (sentinel serve)"), ("jinja2", "Web UI templates")]:
        try:
            __import__(pkg)
            results.append(CheckResult(tool=pkg, status="ok", version="installed", description=desc))
        except ImportError:
            results.append(CheckResult(tool=pkg, status="missing", version="", description=desc))

    # sentinel.toml check
    if repo_path:
        from sentinel.config import ConfigError, load_config

        toml_path = Path(repo_path) / "sentinel.toml"
        try:
            cfg = load_config(repo_path)
            if toml_path.exists():
                results.append(CheckResult(
                    tool="sentinel.toml",
                    status="ok",
                    version=f"provider={cfg.provider}, model={cfg.model}",
                    description="Project configuration",
                ))
            else:
                results.append(CheckResult(
                    tool="sentinel.toml",
                    status="ok",
                    version=f"Using defaults (provider={cfg.provider}, model={cfg.model})",
                    description="No sentinel.toml found — using defaults. Save settings to create one.",
                ))
        except ConfigError as exc:
            results.append(CheckResult(
                tool="sentinel.toml",
                status="error",
                version=str(exc),
                description="Project configuration — validation failed",
            ))
    else:
        results.append(CheckResult(
            tool="sentinel.toml",
            status="missing",
            version="",
            description="Project configuration — no repo path configured",
        ))

    return results
