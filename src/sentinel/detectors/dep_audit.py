"""Dependency audit detector — wraps pip-audit for vulnerability scanning."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import tomllib
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


class DepAudit(Detector):
    """Run pip-audit on a Python project and report known vulnerabilities."""

    @property
    def name(self) -> str:
        return "dep-audit"

    @property
    def description(self) -> str:
        return "Wraps pip-audit to scan for known dependency vulnerabilities"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["dependency"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._run_audit(context)
        except Exception:
            logger.exception("dep-audit failed")
            return []

    def _run_audit(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)

        # Check if this is a Python project
        if not self._is_python_project(repo_root):
            logger.info("No Python project markers found — skipping dep-audit")
            return []

        # Resolve a requirements source for the target repo.
        # This ensures we audit the target's deps, not Sentinel's own env.
        req_file = self._find_requirements(repo_root)
        pyproject_deps = None
        if not req_file:
            pyproject_deps = self._extract_pyproject_deps(repo_root)
            if not pyproject_deps:
                logger.info("No requirements.txt or pyproject.toml dependencies — skipping dep-audit")
                return []

        # Build command: --format json for structured output
        cmd = ["pip-audit", "--format=json", "--output=-"]

        if req_file:
            cmd.extend(["--requirement", str(req_file)])
            return self._exec_audit(cmd, repo_root)

        # Generate a temp requirements file from pyproject.toml deps
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="sentinel-deps-", delete=True
        ) as tmp:
            tmp.write("\n".join(pyproject_deps) + "\n")
            tmp.flush()
            cmd.extend(["--requirement", tmp.name])
            return self._exec_audit(cmd, repo_root)

    def _exec_audit(self, cmd: list[str], repo_root: Path) -> list[Finding]:
        """Execute pip-audit and parse its JSON output."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                timeout=120,
            )
        except FileNotFoundError:
            logger.warning("pip-audit not found — skipping dep-audit")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("pip-audit timed out")
            return []

        if not result.stdout.strip():
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse pip-audit JSON output")
            return []

        findings: list[Finding] = []
        dependencies = data.get("dependencies", [])
        for dep in dependencies:
            vulns = dep.get("vulns", [])
            for vuln in vulns:
                findings.append(self._vuln_to_finding(dep, vuln))

        return findings

    @staticmethod
    def _is_python_project(repo_root: Path) -> bool:
        """Check if the repo looks like a Python project."""
        markers = [
            "pyproject.toml", "setup.py", "setup.cfg",
            "requirements.txt", "Pipfile", "poetry.lock",
        ]
        return any((repo_root / m).exists() for m in markers)

    @staticmethod
    def _find_requirements(repo_root: Path) -> Path | None:
        """Find a requirements file in the repo root."""
        candidates = ["requirements.txt", "requirements-dev.txt"]
        for name in candidates:
            path = repo_root / name
            if path.exists():
                return path
        return None

    @staticmethod
    def _extract_pyproject_deps(repo_root: Path) -> list[str] | None:
        """Extract dependency specifiers from pyproject.toml.

        Returns a list of PEP 508 dependency strings suitable for a
        requirements file, or None if no dependencies are declared.
        """
        pyproject = repo_root / "pyproject.toml"
        if not pyproject.exists():
            return None
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return None

        deps: list[str] = list(data.get("project", {}).get("dependencies", []))
        if not deps:
            return None
        return deps

    @staticmethod
    def _vuln_to_finding(dep: dict, vuln: dict) -> Finding:
        """Convert a pip-audit vulnerability entry to a Finding."""
        pkg_name = dep.get("name", "unknown")
        pkg_version = dep.get("version", "unknown")
        vuln_id = vuln.get("id", "")
        description = vuln.get("description", "No description available")
        fix_versions = vuln.get("fix_versions", [])

        severity = Severity.HIGH  # All known vulns default to high
        # If there are fix versions, it's actionable
        fix_info = f"Fix: upgrade to {', '.join(fix_versions)}" if fix_versions else "No fix available yet"

        return Finding(
            detector="dep-audit",
            category="dependency",
            severity=severity,
            confidence=1.0,
            title=f"{vuln_id}: {pkg_name}=={pkg_version}",
            description=f"Known vulnerability {vuln_id} in {pkg_name} {pkg_version}. {description}",
            evidence=[
                Evidence(
                    type=EvidenceType.AUDIT_OUTPUT,
                    source=f"pip-audit:{vuln_id}",
                    content=f"Package: {pkg_name}=={pkg_version}\n"
                            f"Vulnerability: {vuln_id}\n"
                            f"Description: {description}\n"
                            f"{fix_info}",
                )
            ],
            context={
                "package": pkg_name,
                "version": pkg_version,
                "vuln_id": vuln_id,
                "fix_versions": fix_versions,
            },
        )
