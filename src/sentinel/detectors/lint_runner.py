"""Lint runner detector — wraps ruff and normalizes output into findings."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from sentinel.detectors.base import Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)

logger = logging.getLogger(__name__)

# Map ruff message severity prefixes to Sentinel severities
_SEVERITY_MAP: dict[str, Severity] = {
    "E": Severity.MEDIUM,   # Errors
    "F": Severity.HIGH,     # Pyflakes (unused imports, undefined names)
    "W": Severity.LOW,      # Warnings
    "I": Severity.LOW,      # isort
    "B": Severity.MEDIUM,   # flake8-bugbear
    "S": Severity.HIGH,     # flake8-bandit (security)
    "C": Severity.LOW,      # conventions
}


class LintRunner(Detector):
    """Run ruff check on the target repo and normalize output into findings."""

    @property
    def name(self) -> str:
        return "lint-runner"

    @property
    def description(self) -> str:
        return "Wraps ruff linter and normalizes lint output"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._run_ruff(context)
        except Exception:
            logger.exception("lint-runner failed")
            return []

    def _run_ruff(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)

        # Build command
        cmd = ["ruff", "check", "--output-format=json", "--no-fix"]

        # Scope: specific files or whole repo
        targets = self._get_targets(context, repo_root)
        if targets is not None:
            cmd.extend(targets)
        else:
            cmd.append(".")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                timeout=60,
            )
        except FileNotFoundError:
            logger.warning("ruff not found — skipping lint-runner")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("ruff timed out")
            return []

        # ruff exits non-zero when findings exist — that's normal
        if not result.stdout.strip():
            return []

        try:
            violations = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse ruff JSON output")
            return []

        findings: list[Finding] = []
        for v in violations:
            findings.append(self._violation_to_finding(v, repo_root))
        return findings

    def _get_targets(
        self, context: DetectorContext, repo_root: Path
    ) -> list[str] | None:
        """Return file targets based on scope, or None for full scan."""
        if context.scope.value == "incremental" and context.changed_files:
            return [
                f for f in context.changed_files
                if f.endswith(".py") and (repo_root / f).is_file()
            ]
        if context.scope.value == "targeted" and context.target_paths:
            return [
                f for f in context.target_paths
                if f.endswith(".py") and (repo_root / f).is_file()
            ]
        return None

    @staticmethod
    def _violation_to_finding(v: dict, repo_root: Path) -> Finding:
        """Convert a single ruff JSON violation to a Finding."""
        code = v.get("code", "")
        message = v.get("message", "")
        filename = v.get("filename", "")

        # Make path relative to repo root
        try:
            rel_path = str(Path(filename).relative_to(repo_root))
        except ValueError:
            rel_path = filename

        line_start = v.get("location", {}).get("row", 0)
        line_end = v.get("end_location", {}).get("row", line_start)

        # Build source snippet from the fix or message
        content_lines = [f"{code}: {message}"]
        fix = v.get("fix")
        if fix and fix.get("message"):
            content_lines.append(f"Fix: {fix['message']}")

        severity = _SEVERITY_MAP.get(code[0] if code else "", Severity.MEDIUM)

        return Finding(
            detector="lint-runner",
            category="code-quality",
            severity=severity,
            confidence=1.0,  # Deterministic linter output
            title=f"{code}: {message}",
            description=f"ruff {code} in {rel_path}:{line_start} — {message}",
            evidence=[
                Evidence(
                    type=EvidenceType.LINT_OUTPUT,
                    source=f"ruff:{code}",
                    content="\n".join(content_lines),
                    line_range=(line_start, line_end) if line_start else None,
                )
            ],
            file_path=rel_path,
            line_start=line_start,
            line_end=line_end,
            context={"rule": code, "fix": fix},
        )
