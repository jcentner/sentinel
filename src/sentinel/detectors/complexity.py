"""Complexity detector — identifies overly complex or long functions via AST analysis."""

from __future__ import annotations

import ast
import logging
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

# Thresholds (configurable via detector context config in the future)
_MAX_FUNCTION_LINES = 50
_MAX_CYCLOMATIC_COMPLEXITY = 10

# Only scan Python files
_PYTHON_EXTENSIONS = {".py"}

# Directories to skip
_SKIP_DIRS = COMMON_SKIP_DIRS


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Calculate McCabe cyclomatic complexity for a function/method node.

    Complexity = 1 + number of decision points (if, elif, for, while,
    except, and, or, assert, ternary).
    """
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp, ast.For, ast.While,
                              ast.ExceptHandler, ast.Assert)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # `and`/`or` add len(values)-1 decision points
            complexity += len(child.values) - 1
    return complexity


def _function_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count lines in a function body (end_lineno - start of first body stmt)."""
    if not node.body:
        return 0
    first_line = node.body[0].lineno
    end_line = node.end_lineno or node.lineno
    return end_line - first_line + 1


class ComplexityDetector(Detector):
    """Detects overly complex or long Python functions."""

    @property
    def name(self) -> str:
        return "complexity"

    @property
    def description(self) -> str:
        return "Flags Python functions exceeding complexity or length thresholds"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.HEURISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        findings: list[Finding] = []
        try:
            files = self._get_python_files(context)
            for file_path in files:
                findings.extend(self._analyze_file(file_path, context.repo_root))
        except Exception:
            logger.exception("complexity detector failed")
        return findings

    def _get_python_files(self, context: DetectorContext) -> list[Path]:
        """Collect Python files to analyze."""
        root = Path(context.repo_root)

        if context.target_paths:
            files = []
            for tp in context.target_paths:
                p = root / tp
                if p.is_file() and p.suffix in _PYTHON_EXTENSIONS:
                    files.append(p)
                elif p.is_dir():
                    files.extend(self._walk_dir(p))
            return files

        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            return [
                root / f for f in context.changed_files
                if f.endswith(".py") and (root / f).is_file()
            ]

        return self._walk_dir(root)

    def _walk_dir(self, directory: Path) -> list[Path]:
        """Recursively collect .py files, skipping known directories."""
        files: list[Path] = []
        try:
            for item in sorted(directory.iterdir()):
                if item.is_dir():
                    if item.name not in _SKIP_DIRS and not item.name.endswith(".egg-info"):
                        files.extend(self._walk_dir(item))
                elif item.is_file() and item.suffix in _PYTHON_EXTENSIONS:
                    files.append(item)
        except PermissionError:
            pass
        return files

    def _analyze_file(self, file_path: Path, repo_root: str) -> list[Finding]:
        """Parse a Python file and check all functions for complexity."""
        findings: list[Finding] = []
        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return findings

        rel_path = str(file_path.relative_to(repo_root))

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = node.name
            cc = _cyclomatic_complexity(node)
            lines = _function_lines(node)

            # Check both thresholds
            issues: list[str] = []
            if cc > _MAX_CYCLOMATIC_COMPLEXITY:
                issues.append(f"cyclomatic complexity {cc} (threshold: {_MAX_CYCLOMATIC_COMPLEXITY})")
            if lines > _MAX_FUNCTION_LINES:
                issues.append(f"{lines} lines (threshold: {_MAX_FUNCTION_LINES})")

            if not issues:
                continue

            # Determine severity from how far over threshold
            severity = self._severity_for(cc, lines)
            confidence = 0.95  # AST measurement is deterministic; threshold choice is heuristic

            description = f"`{func_name}` has " + " and ".join(issues) + "."
            title = f"Complex function: {func_name} ({', '.join(issues)})"

            evidence = [
                Evidence(
                    type=EvidenceType.CODE,
                    content=f"Function {func_name} at {rel_path}:{node.lineno}",
                    source=rel_path,
                    line_range=(node.lineno, node.end_lineno or node.lineno),
                ),
            ]

            findings.append(Finding(
                detector=self.name,
                category="code-quality",
                severity=severity,
                confidence=confidence,
                title=title,
                description=description,
                evidence=evidence,
                file_path=rel_path,
                line_start=node.lineno,
                line_end=node.end_lineno,
            ))

        return findings

    def _severity_for(self, cc: int, lines: int) -> Severity:
        """Map complexity metrics to severity."""
        if cc > _MAX_CYCLOMATIC_COMPLEXITY * 2 or lines > _MAX_FUNCTION_LINES * 3:
            return Severity.HIGH
        if cc > _MAX_CYCLOMATIC_COMPLEXITY * 1.5 or lines > _MAX_FUNCTION_LINES * 2:
            return Severity.MEDIUM
        return Severity.LOW
