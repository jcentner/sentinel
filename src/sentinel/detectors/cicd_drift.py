"""CI/CD config drift detector.

Detects stale file/directory references in CI/CD configuration files:
- GitHub Actions workflows: local action paths, working-directory, path-valued keys
- Dockerfiles: COPY/ADD source paths

This is a deterministic cross-artifact check — every finding cites a
concrete path reference in a config file and the fact that the path
does not exist in the repository.
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
    Severity,
)

logger = logging.getLogger(__name__)

# GitHub Actions keys whose values are repo-relative paths.
# These appear in step-level `with:` blocks or job-level settings.
_GHA_PATH_KEYS: frozenset[str] = frozenset({
    "working-directory",
    "path",
    "file",
    "entrypoint",
})

# Dockerfile instructions that take a source path as their first argument.
_DOCKERFILE_COPY_RE = re.compile(
    r"^\s*(?:COPY|ADD)\s+"      # instruction
    r"(?:--[a-z-]+=\S+\s+)*"   # optional flags like --chown=...
    r"(\S+)",                   # first positional arg = source
    re.IGNORECASE,
)

# Patterns that indicate the path is not a local file reference.
_NON_PATH_INDICATORS = re.compile(
    r"^(?:https?://|ftp://|\$|--)",
    re.IGNORECASE,
)


class CicdDrift(Detector):
    """Detect stale path references in CI/CD configuration files."""

    @property
    def name(self) -> str:
        return "cicd-drift"

    @property
    def description(self) -> str:
        return "Detects stale path references in GitHub Actions and Dockerfiles"

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
            logger.exception("cicd-drift failed")
            return []

    def _run(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)
        findings: list[Finding] = []
        findings.extend(self._check_github_actions(repo_root))
        findings.extend(self._check_dockerfiles(repo_root))
        return findings

    # ------------------------------------------------------------------
    # GitHub Actions
    # ------------------------------------------------------------------

    def _check_github_actions(self, repo_root: Path) -> list[Finding]:
        """Check .github/workflows/*.yml for stale path references."""
        workflows_dir = repo_root / ".github" / "workflows"
        if not workflows_dir.is_dir():
            return []

        findings: list[Finding] = []
        for wf_path in sorted(workflows_dir.iterdir()):
            if wf_path.suffix not in {".yml", ".yaml"}:
                continue
            try:
                content = wf_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            rel_path = str(wf_path.relative_to(repo_root))
            findings.extend(
                self._check_gha_content(repo_root, rel_path, content),
            )
        return findings

    def _check_gha_content(
        self,
        repo_root: Path,
        wf_rel_path: str,
        content: str,
    ) -> list[Finding]:
        """Parse a single workflow file for stale path references."""
        findings: list[Finding] = []
        lines = content.splitlines()

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Strip YAML list marker if present
            if stripped.startswith("- "):
                stripped = stripped[2:].strip()

            # Local action: uses: ./path/to/action
            if stripped.startswith("uses:"):
                value = stripped.split(":", 1)[1].strip().strip("'\"")
                if value.startswith("./"):
                    ref_path = value.rstrip("/")
                    if not (repo_root / ref_path).exists():
                        findings.append(self._make_finding(
                            repo_root=repo_root,
                            config_file=wf_rel_path,
                            line_num=line_num,
                            line_text=stripped,
                            ref_path=ref_path,
                            kind="local action",
                        ))
                continue

            # Key-value pairs like working-directory: path
            for key in _GHA_PATH_KEYS:
                prefix = f"{key}:"
                if stripped.startswith(prefix):
                    value = stripped[len(prefix):].strip().strip("'\"")
                    if not value or value.startswith("$") or value.startswith("{"):
                        break  # templated / dynamic — skip
                    if _is_glob_pattern(value):
                        break  # glob — skip
                    if value.startswith("/") or value.startswith("~"):
                        break  # absolute / home-relative — not repo paths
                    if not (repo_root / value).exists():
                        findings.append(self._make_finding(
                            repo_root=repo_root,
                            config_file=wf_rel_path,
                            line_num=line_num,
                            line_text=stripped,
                            ref_path=value,
                            kind=key,
                        ))
                    break  # matched a key, stop checking others

        return findings

    # ------------------------------------------------------------------
    # Dockerfiles
    # ------------------------------------------------------------------

    def _check_dockerfiles(self, repo_root: Path) -> list[Finding]:
        """Check Dockerfile* for COPY/ADD source paths that don't exist."""
        findings: list[Finding] = []
        for path in sorted(repo_root.rglob("Dockerfile*")):
            if not path.is_file():
                continue
            if any(part in COMMON_SKIP_DIRS for part in path.parts):
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            rel_path = str(path.relative_to(repo_root))
            dockerfile_dir = path.parent
            findings.extend(
                self._check_dockerfile_content(
                    repo_root, rel_path, content, dockerfile_dir,
                ),
            )
        return findings

    def _check_dockerfile_content(
        self,
        repo_root: Path,
        dockerfile_rel_path: str,
        content: str,
        dockerfile_dir: Path | None = None,
    ) -> list[Finding]:
        """Parse a Dockerfile for COPY/ADD with missing source paths.

        Checks source paths relative to both repo_root (common when
        ``docker build -f subdir/Dockerfile .``) and the Dockerfile's
        own directory (common when ``docker build subdir/``). A finding
        is created only when the path is missing from *both* locations.

        Note: multi-source COPY (``COPY a b c /dest/``) only checks the
        first source argument.
        """
        findings: list[Finding] = []
        lines = content.splitlines()

        for line_num, line in enumerate(lines, start=1):
            match = _DOCKERFILE_COPY_RE.match(line)
            if not match:
                continue

            source = match.group(1)

            # Skip non-local sources
            if _NON_PATH_INDICATORS.match(source):
                continue
            # Skip build-arg interpolation
            if "$" in source:
                continue
            # Skip COPY --from=stage references (multi-stage builds)
            if re.search(r"--from=", line, re.IGNORECASE):
                continue
            # Skip glob patterns (COPY *.txt .)
            if _is_glob_pattern(source):
                continue
            # Skip the current-directory case (COPY . .)
            if source in {".", "./"}:
                continue

            if not (repo_root / source).exists() and not (
                dockerfile_dir and (dockerfile_dir / source).exists()
            ):
                findings.append(self._make_finding(
                    repo_root=repo_root,
                    config_file=dockerfile_rel_path,
                    line_num=line_num,
                    line_text=line.strip(),
                    ref_path=source,
                    kind="COPY/ADD source",
                ))

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_finding(
        self,
        *,
        repo_root: Path,
        config_file: str,
        line_num: int,
        line_text: str,
        ref_path: str,
        kind: str,
    ) -> Finding:
        """Create a Finding for a stale path reference."""
        return Finding(
            detector=self.name,
            category="config-drift",
            title=f"Stale {kind} reference: {ref_path}",
            description=(
                f"The {kind} reference '{ref_path}' in {config_file} "
                f"(line {line_num}) points to a path that does not exist "
                f"in the repository."
            ),
            file_path=config_file,
            line_start=line_num,
            line_end=line_num,
            severity=Severity.MEDIUM,
            confidence=0.90,
            evidence=[Evidence(
                type=EvidenceType.CONFIG,
                source=config_file,
                content=line_text,
                line_range=(line_num, line_num),
            )],
        )


def _is_glob_pattern(value: str) -> bool:
    """Check if a value looks like a glob pattern rather than a literal path."""
    return bool(set(value) & {"*", "?", "[", "{", "}"})
