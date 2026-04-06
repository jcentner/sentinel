"""Go linter detector — wraps golangci-lint and normalizes output into findings."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from sentinel.detectors.base import Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    ScopeType,
    Severity,
)

logger = logging.getLogger(__name__)

_GO_EXTENSIONS = frozenset({".go"})
_SKIP_DIRS = frozenset({".git", ".sentinel", "vendor", "node_modules", ".venv"})

# Map golangci-lint severity to Sentinel severity
_SEVERITY_MAP: dict[str, Severity] = {
    "error": Severity.MEDIUM,
    "warning": Severity.LOW,
    "info": Severity.LOW,
}

# Linters whose findings indicate higher severity
_HIGH_SEVERITY_LINTERS = frozenset({
    "gosec",       # Security issues
    "govet",       # Suspicious constructs
    "staticcheck", # Static analysis
    "errcheck",    # Unchecked errors
})


def _has_go_files(repo_root: Path) -> bool:
    """Quick check for Go files in the repo."""
    if (repo_root / "go.mod").is_file():
        return True
    for p in repo_root.rglob("*"):
        if _SKIP_DIRS & set(p.relative_to(repo_root).parts):
            continue
        if p.is_file() and p.suffix in _GO_EXTENSIONS:
            return True
    return False


class GoLinter(Detector):
    """Run golangci-lint on Go repos and normalize output into findings."""

    @property
    def name(self) -> str:
        return "go-linter"

    @property
    def description(self) -> str:
        return "Wraps golangci-lint for Go linting"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)

        if not _has_go_files(repo_root):
            logger.debug("go-linter: no Go files found — skipping")
            return []

        findings = self._try_golangci_lint(context, repo_root)
        if findings is not None:
            return findings

        logger.debug("go-linter: golangci-lint not found — skipping")
        return []

    def _try_golangci_lint(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Finding] | None:
        """Run golangci-lint and return findings, or None if not available."""
        try:
            targets = self._get_targets(context, repo_root)
            cmd = [
                "golangci-lint", "run",
                "--out-format=json",
                "--timeout=120s",
            ]
            if targets:
                cmd.extend(targets)
            else:
                cmd.append("./...")

            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=150,
            )
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            logger.warning("go-linter: golangci-lint timed out")
            return []

        return self._parse_output(result.stdout, repo_root)

    def _parse_output(
        self, stdout: str, repo_root: Path
    ) -> list[Finding]:
        """Parse golangci-lint JSON output into findings."""
        if not stdout.strip():
            return []

        try:
            data: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("go-linter: failed to parse golangci-lint JSON output")
            return []

        issues: list[dict[str, Any]] = data.get("Issues", []) or []
        findings: list[Finding] = []

        for issue in issues:
            text: str = issue.get("Text", "")
            from_linter: str = issue.get("FromLinter", "unknown")
            pos: dict[str, Any] = issue.get("Pos", {})
            filename: str = pos.get("Filename", "")
            line: int = pos.get("Line", 0)
            severity_str: str = issue.get("Severity", "warning")

            # Determine severity
            if from_linter in _HIGH_SEVERITY_LINTERS:
                severity = Severity.HIGH
            else:
                severity = _SEVERITY_MAP.get(severity_str, Severity.LOW)

            rel_path = filename
            evidence = Evidence(
                type=EvidenceType.LINT_OUTPUT,
                content=f"{rel_path}:{line}: {text}",
                source=rel_path,
                line_range=(line, line) if line else None,
            )

            findings.append(Finding(
                title=f"[{from_linter}] {text}",
                description=f"golangci-lint ({from_linter}): {text}",
                detector=self.name,
                category="code-quality",
                severity=severity,
                confidence=1.0,
                file_path=rel_path,
                line_start=line if line else None,
                evidence=[evidence],                context={"linter": from_linter, "tool": "golangci-lint"},            ))

        return findings

    def _get_targets(
        self, context: DetectorContext, repo_root: Path
    ) -> list[str]:
        """Get target paths for golangci-lint based on scan scope."""
        paths: list[str] = []

        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            paths = [f for f in context.changed_files if Path(f).suffix in _GO_EXTENSIONS]
        elif context.target_paths:
            paths = list(context.target_paths)
        else:
            return []

        targets: list[str] = []
        for t in paths:
            tp = Path(t)
            if tp.is_absolute():
                try:
                    tp = tp.relative_to(repo_root)
                except ValueError:
                    continue
            if tp.suffix in _GO_EXTENSIONS:
                # golangci-lint runs on packages, not individual files
                targets.append(f"./{tp.parent}/...")
            elif (repo_root / tp).is_dir():
                targets.append(f"./{tp}/...")

        return list(set(targets))  # deduplicate
