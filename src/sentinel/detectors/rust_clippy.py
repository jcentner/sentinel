"""Rust linter detector — wraps cargo clippy and normalizes output into findings."""

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

_RS_EXTENSIONS = frozenset({".rs"})
_SKIP_DIRS = frozenset({".git", ".sentinel", "target", "node_modules", ".venv"})

# Map Rust diagnostic level to Sentinel severity
_SEVERITY_MAP: dict[str, Severity] = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "note": Severity.LOW,
    "help": Severity.LOW,
    "ice": Severity.HIGH,  # internal compiler error
}

# Clippy lint groups whose findings should be elevated to HIGH
_HIGH_SEVERITY_LINTS = frozenset({
    "clippy::correctness",
    "clippy::suspicious",
    "clippy::security",
})

# Prefixes for lint names that indicate high severity
_HIGH_SEVERITY_PREFIXES = (
    "clippy::correctness",
    "clippy::suspicious",
)


def _has_rust_files(repo_root: Path) -> bool:
    """Quick check for Rust files in the repo."""
    if (repo_root / "Cargo.toml").is_file():
        return True
    for p in repo_root.rglob("*"):
        if _SKIP_DIRS & set(p.parts):
            continue
        if p.is_file() and p.suffix in _RS_EXTENSIONS:
            return True
    return False


def _is_high_severity_lint(lint_name: str) -> bool:
    """Check if a clippy lint name indicates high severity."""
    if lint_name in _HIGH_SEVERITY_LINTS:
        return True
    return any(lint_name.startswith(prefix) for prefix in _HIGH_SEVERITY_PREFIXES)


class RustClippy(Detector):
    """Run cargo clippy on Rust repos and normalize output into findings."""

    @property
    def name(self) -> str:
        return "rust-clippy"

    @property
    def description(self) -> str:
        return "Wraps cargo clippy for Rust linting"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)

        if not _has_rust_files(repo_root):
            logger.debug("rust-clippy: no Rust files found — skipping")
            return []

        findings = self._try_clippy(context, repo_root)
        if findings is not None:
            return findings

        logger.debug("rust-clippy: cargo not found — skipping")
        return []

    def _try_clippy(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Finding] | None:
        """Run cargo clippy and return findings, or None if not available."""
        try:
            cmd = [
                "cargo", "clippy",
                "--message-format=json",
                "--quiet",
            ]

            # For targeted scans, clippy doesn't support per-file targeting
            # but we can filter results afterward
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            logger.warning("rust-clippy: cargo clippy timed out")
            return []

        findings = self._parse_output(result.stdout, repo_root)

        # Filter findings to targeted/incremental scope
        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            rs_files = {f for f in context.changed_files if Path(f).suffix in _RS_EXTENSIONS}
            findings = [f for f in findings if f.file_path and f.file_path in rs_files]
        elif context.scope == ScopeType.TARGETED and context.target_paths:
            targets = set(context.target_paths)
            findings = [
                f for f in findings
                if f.file_path and (
                    f.file_path in targets
                    or any(f.file_path.startswith(str(t) + "/") for t in targets)
                )
            ]

        return findings

    def _parse_output(
        self, stdout: str, repo_root: Path
    ) -> list[Finding]:
        """Parse cargo clippy JSON output into findings.

        Cargo outputs one JSON object per line (JSON Lines format).
        We only care about messages with reason="compiler-message".
        """
        if not stdout.strip():
            return []

        findings: list[Finding] = []
        seen: set[str] = set()  # deduplicate by (file, line, message)

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                msg: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue

            if msg.get("reason") != "compiler-message":
                continue

            diag: dict[str, Any] = msg.get("message", {})
            if not diag:
                continue

            level: str = diag.get("level", "warning")
            message: str = diag.get("message", "")
            code_info: dict[str, Any] | None = diag.get("code")
            lint_name: str = code_info.get("code", "") if code_info else ""

            # Extract primary span (file location)
            spans: list[dict[str, Any]] = diag.get("spans", [])
            primary_span = next(
                (s for s in spans if s.get("is_primary")),
                spans[0] if spans else None,
            )

            if not primary_span:
                continue

            filename: str = primary_span.get("file_name", "")
            line_start: int = primary_span.get("line_start", 0)
            line_end: int = primary_span.get("line_end", 0)

            # Skip compiler internals and build script output
            if not filename or filename.startswith("/"):
                continue

            # Deduplicate
            dedup_key = f"{filename}:{line_start}:{message}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Determine severity
            if _is_high_severity_lint(lint_name):
                severity = Severity.HIGH
            else:
                severity = _SEVERITY_MAP.get(level, Severity.MEDIUM)

            snippet: str = primary_span.get("text", [{}])[0].get("text", "") if primary_span.get("text") else ""
            evidence_content = f"{filename}:{line_start}: {message}"
            if snippet:
                evidence_content += f"\n  {snippet}"

            evidence = Evidence(
                type=EvidenceType.LINT_OUTPUT,
                content=evidence_content,
                source=filename,
                line_range=(line_start, line_end) if line_start else None,
            )

            title_prefix = f"[{lint_name}]" if lint_name else f"[{level}]"
            findings.append(Finding(
                title=f"{title_prefix} {message}",
                description=f"cargo clippy: {message}",
                detector=self.name,
                category="code-quality",
                severity=severity,
                confidence=1.0,
                file_path=filename,
                line_start=line_start if line_start else None,
                evidence=[evidence],
                context={"lint": lint_name, "tool": "cargo-clippy"},
            ))

        return findings
