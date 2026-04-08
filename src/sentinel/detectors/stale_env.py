"""Stale config / env drift detector.

Compares environment variable documentation (.env.example, .env.sample)
against actual env var references in source code. Detects:
- Documented vars never referenced in code (stale docs)
- Code references to vars not documented in the example file

This is a cross-artifact consistency check that catches config drift
after rapid development — variables get added to code but not the
example file, or old variables linger in the example after removal.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sentinel.detectors.base import COMMON_SKIP_DIRS, Detector
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

# Standard env vars that apps commonly use but shouldn't flag
_COMMON_ENV_VARS: frozenset[str] = frozenset({
    # System/runtime
    "PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "TZ",
    "PWD", "TERM", "TMPDIR", "TEMP", "TMP",
    # Python
    "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
    "VIRTUAL_ENV",
    # Node
    "NODE_ENV", "NODE_PATH", "NODE_OPTIONS", "NPM_TOKEN",
    # CI/CD
    "CI", "GITHUB_ACTIONS", "GITHUB_TOKEN", "GITHUB_REF",
    "GITHUB_SHA", "GITHUB_REPOSITORY",
    # Docker
    "DOCKER_HOST", "COMPOSE_PROJECT_NAME",
})

# Patterns to extract env var names from Python source
_PY_ENV_PATTERNS: list[re.Pattern[str]] = [
    # os.environ["VAR"], os.environ.get("VAR"), os.getenv("VAR")
    re.compile(r"""os\.environ\[['"]([A-Z_][A-Z0-9_]*)['"]"""),
    re.compile(r"""os\.environ\.get\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
    re.compile(r"""os\.getenv\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
]

# Patterns to extract env var names from JS/TS source
_JS_ENV_PATTERNS: list[re.Pattern[str]] = [
    # process.env.VAR_NAME
    re.compile(r"""process\.env\.([A-Z_][A-Z0-9_]*)"""),
    # process.env["VAR_NAME"] or process.env['VAR_NAME']
    re.compile(r"""process\.env\[['"]([A-Z_][A-Z0-9_]*)['"]"""),
]


class StaleEnv(Detector):
    """Detect drift between env var documentation and actual code references."""

    @property
    def name(self) -> str:
        return "stale-env"

    @property
    def description(self) -> str:
        return "Detects drift between .env.example and env var usage in code"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["config-drift"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._run(context)
        except Exception:
            logger.exception("stale-env failed")
            return []

    def _run(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)
        findings: list[Finding] = []

        # Find env example file
        example_file, documented_vars = self._read_env_example(repo_root)
        if not example_file:
            logger.debug("No .env.example/.env.sample found — skipping stale-env")
            return []

        # Collect env var references from source
        code_vars = self._collect_code_env_vars(repo_root, context)

        # Filter out common system vars
        documented_filtered = documented_vars - _COMMON_ENV_VARS
        code_filtered = code_vars - _COMMON_ENV_VARS

        # Documented but never referenced in code
        for var in sorted(documented_filtered - code_filtered):
            findings.append(Finding(
                detector=self.name,
                category="config-drift",
                title=f"Documented env var never used: {var}",
                description=(
                    f"Environment variable '{var}' is documented in {example_file} "
                    f"but no reference was found in source code. "
                    f"It may be stale after code changes."
                ),
                file_path=example_file,
                severity=Severity.LOW,
                confidence=0.80,
                evidence=[Evidence(
                    type=EvidenceType.CONFIG,
                    source=example_file,
                    content=f"Documented: {var}",
                )],
            ))

        # Referenced in code but not documented
        for var in sorted(code_filtered - documented_filtered):
            findings.append(Finding(
                detector=self.name,
                category="config-drift",
                title=f"Undocumented env var: {var}",
                description=(
                    f"Environment variable '{var}' is referenced in source code "
                    f"but not documented in {example_file}. "
                    f"New developers may not know to set it."
                ),
                file_path=example_file,
                severity=Severity.MEDIUM,
                confidence=0.75,
                evidence=[Evidence(
                    type=EvidenceType.CONFIG,
                    source=example_file,
                    content=f"Missing from docs: {var}",
                )],
            ))

        return findings

    def _read_env_example(self, repo_root: Path) -> tuple[str | None, set[str]]:
        """Read the env example file and extract documented variable names."""
        candidates = [
            ".env.example", ".env.sample", ".env.template",
            "env.example", "env.sample",
        ]

        for name in candidates:
            path = repo_root / name
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                variables = self._parse_env_file(content)
                if variables:
                    return name, variables

        return None, set()

    @staticmethod
    def _parse_env_file(content: str) -> set[str]:
        """Extract variable names from a .env-format file."""
        variables: set[str] = set()
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and blank lines
            if not line or line.startswith("#"):
                continue
            # Match KEY=value or KEY= or just KEY (some examples omit values)
            match = re.match(r"^([A-Z_][A-Z0-9_]*)(?:\s*=.*)?$", line)
            if match:
                variables.add(match.group(1))
        return variables

    def _collect_code_env_vars(
        self, repo_root: Path, context: DetectorContext,
    ) -> set[str]:
        """Collect all env var names referenced in source code."""
        env_vars: set[str] = set()

        # Scan Python files
        for py_file in self._get_files(repo_root, context, {".py"}):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern in _PY_ENV_PATTERNS:
                for match in pattern.finditer(content):
                    env_vars.add(match.group(1))

        # Scan JS/TS files
        js_exts = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
        for js_file in self._get_files(repo_root, context, js_exts):
            try:
                content = js_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern in _JS_ENV_PATTERNS:
                for match in pattern.finditer(content):
                    env_vars.add(match.group(1))

        return env_vars

    def _get_files(
        self,
        repo_root: Path,
        context: DetectorContext,
        extensions: set[str],
    ) -> list[Path]:
        """Get source files to scan, respecting scope."""
        if context.target_paths:
            files: list[Path] = []
            for tp in context.target_paths:
                p = Path(tp)
                if not p.is_absolute():
                    p = repo_root / p
                if p.is_file() and p.suffix in extensions:
                    files.append(p)
                elif p.is_dir():
                    files.extend(self._walk_files(p, extensions))
            return files

        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            return [
                repo_root / f for f in context.changed_files
                if any(f.endswith(ext) for ext in extensions)
                and (repo_root / f).exists()
            ]

        return self._walk_files(repo_root, extensions)

    @staticmethod
    def _walk_files(root: Path, extensions: set[str]) -> list[Path]:
        """Walk directory for files with given extensions."""
        files: list[Path] = []
        for ext in extensions:
            for path in root.rglob(f"*{ext}"):
                if any(part in COMMON_SKIP_DIRS for part in path.parts):
                    continue
                files.append(path)
        return files
