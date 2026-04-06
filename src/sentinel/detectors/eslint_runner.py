"""ESLint/Biome detector — wraps JS/TS linters and normalizes output into findings."""

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
    Severity,
)

logger = logging.getLogger(__name__)

_JS_EXTENSIONS = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"})

# Map ESLint severity levels (1=warn, 2=error) to Sentinel severities
_ESLINT_SEVERITY_MAP: dict[int, Severity] = {
    1: Severity.LOW,
    2: Severity.MEDIUM,
}

# ESLint rules that indicate higher severity
_ESLINT_HIGH_RULES = frozenset({
    "no-eval", "no-implied-eval", "no-new-func",
    "no-script-url", "no-proto",
})

# Biome diagnostic severity mapping
_BIOME_SEVERITY_MAP: dict[str, Severity] = {
    "error": Severity.MEDIUM,
    "warning": Severity.LOW,
    "information": Severity.LOW,
    "hint": Severity.LOW,
}

# Biome rule categories that indicate higher severity
_BIOME_HIGH_CATEGORIES = frozenset({
    "suspicious", "security",
})


def _has_js_files(repo_root: Path) -> bool:
    """Quick check for JS/TS files in the repo root."""
    if (repo_root / "package.json").is_file():
        return True
    # Check for any JS/TS files, skipping vendored/hidden dirs
    _SKIP_DIRS = frozenset({".git", ".sentinel", "node_modules", "dist", "build", ".venv", "__pycache__"})
    for p in repo_root.rglob("*"):
        if _SKIP_DIRS & set(p.parts):
            continue
        if p.is_file() and p.suffix in _JS_EXTENSIONS:
            return True
    return False


class EslintRunner(Detector):
    """Run ESLint or Biome on JS/TS files and normalize output into findings."""

    @property
    def name(self) -> str:
        return "eslint-runner"

    @property
    def description(self) -> str:
        return "Wraps ESLint/Biome for JavaScript/TypeScript linting"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)

        if not _has_js_files(repo_root):
            logger.debug("eslint-runner: no JS/TS files found — skipping")
            return []

        try:
            # Try biome first (faster, zero-config), then eslint
            findings = self._try_biome(context, repo_root)
            if findings is not None:
                return findings

            findings = self._try_eslint(context, repo_root)
            if findings is not None:
                return findings
        except Exception:
            logger.exception("eslint-runner: unexpected error")
            return []

        logger.warning("eslint-runner: neither biome nor eslint found — skipping")
        return []

    def _try_biome(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Finding] | None:
        """Try running Biome. Returns None if biome is not available."""
        cmd = ["biome", "lint", "--reporter=json"]

        targets = self._get_targets(context, repo_root)
        if targets is not None:
            if not targets:
                return []
            cmd.extend(targets)
        else:
            cmd.append(".")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                timeout=120,
            )
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            logger.warning("biome timed out")
            return []

        if not result.stdout.strip():
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse biome JSON output")
            return []

        return self._parse_biome_output(data, repo_root)

    def _try_eslint(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Finding] | None:
        """Try running ESLint. Returns None if eslint is not available."""
        cmd = ["eslint", "--format=json", "--no-error-on-unmatched-pattern"]

        targets = self._get_targets(context, repo_root)
        if targets is not None:
            if not targets:
                return []
            cmd.extend(targets)
        else:
            cmd.append(".")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                timeout=120,
            )
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            logger.warning("eslint timed out")
            return []

        if not result.stdout.strip():
            return []

        try:
            file_results = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse eslint JSON output")
            return []

        return self._parse_eslint_output(file_results, repo_root)

    def _get_targets(
        self, context: DetectorContext, repo_root: Path
    ) -> list[str] | None:
        """Return JS/TS file targets based on scope, or None for full scan."""
        if context.scope.value == "incremental" and context.changed_files:
            return [
                f for f in context.changed_files
                if Path(f).suffix in _JS_EXTENSIONS and (repo_root / f).is_file()
            ]
        if context.scope.value == "targeted" and context.target_paths:
            return [
                f for f in context.target_paths
                if Path(f).suffix in _JS_EXTENSIONS and (repo_root / f).is_file()
            ]
        return None

    @staticmethod
    def _parse_eslint_output(
        file_results: list[dict[str, Any]], repo_root: Path
    ) -> list[Finding]:
        """Parse ESLint JSON output into findings."""
        findings: list[Finding] = []
        for file_result in file_results:
            filepath = file_result.get("filePath", "")
            try:
                rel_path = str(Path(filepath).relative_to(repo_root))
            except ValueError:
                rel_path = filepath

            for msg in file_result.get("messages", []):
                rule_id = msg.get("ruleId") or "unknown"
                message = msg.get("message", "")
                line = msg.get("line", 0)
                end_line = msg.get("endLine", line)
                eslint_sev = msg.get("severity", 1)

                severity = _ESLINT_SEVERITY_MAP.get(eslint_sev, Severity.MEDIUM)
                if rule_id in _ESLINT_HIGH_RULES:
                    severity = Severity.HIGH

                findings.append(Finding(
                    detector="eslint-runner",
                    category="code-quality",
                    severity=severity,
                    confidence=1.0,
                    title=f"{rule_id}: {message}",
                    description=f"eslint {rule_id} in {rel_path}:{line} — {message}",
                    evidence=[Evidence(
                        type=EvidenceType.LINT_OUTPUT,
                        source=f"eslint:{rule_id}",
                        content=f"{rule_id}: {message}",
                        line_range=(line, end_line) if line else None,
                    )],
                    file_path=rel_path,
                    line_start=line,
                    line_end=end_line,
                    context={"rule": rule_id, "tool": "eslint"},
                ))
        return findings

    @staticmethod
    def _parse_biome_output(
        data: dict[str, Any], repo_root: Path
    ) -> list[Finding]:
        """Parse Biome JSON reporter output into findings."""
        findings: list[Finding] = []
        diagnostics = data.get("diagnostics", [])

        for diag in diagnostics:
            category = diag.get("category", "")
            message_parts = diag.get("message", [])
            message = "".join(
                p.get("content", "") if isinstance(p, dict) else str(p)
                for p in message_parts
            ) if isinstance(message_parts, list) else str(message_parts)

            sev_str = diag.get("severity", "warning")
            severity = _BIOME_SEVERITY_MAP.get(sev_str, Severity.MEDIUM)

            # Elevate severity for suspicious/security rules
            category_parts = category.split("/")
            if any(part in _BIOME_HIGH_CATEGORIES for part in category_parts):
                severity = Severity.HIGH

            location = diag.get("location", {})
            filepath = location.get("path", {}).get("file", "")
            try:
                rel_path = str(Path(filepath).relative_to(repo_root))
            except ValueError:
                rel_path = filepath

            findings.append(Finding(
                detector="eslint-runner",
                category="code-quality",
                severity=severity,
                confidence=1.0,
                title=f"{category}: {message}",
                description=f"biome {category} in {rel_path} — {message}",
                evidence=[Evidence(
                    type=EvidenceType.LINT_OUTPUT,
                    source=f"biome:{category}",
                    content=f"{category}: {message}",
                    line_range=None,  # Biome uses byte spans, not lines
                )],
                file_path=rel_path if filepath else None,
                line_start=None,  # byte offsets not useful as line numbers
                line_end=None,
                context={"rule": category, "tool": "biome"},
            ))
        return findings
