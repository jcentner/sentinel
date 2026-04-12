"""Architecture drift detector — checks import graph against declared layer rules.

Detects imports that violate documented architecture boundaries:
- Lower layer importing from higher layer (layer violation)
- Explicitly forbidden cross-module imports

Rules are declared in sentinel.toml:

    [sentinel.architecture]
    layers = [
        "myapp.web",       # highest layer
        "myapp.core",
        "myapp.store",
        "myapp.models",    # lowest layer
    ]
    shared = ["myapp.models", "myapp.config"]
    forbidden = ["myapp.store -> myapp.web"]

Layers are ordered highest to lowest. Lower layers must not import
from higher layers. Shared modules are exempt from layer checks.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

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

# Parse "a.b.c -> x.y.z" forbidden rule
_ARROW_RE = re.compile(r"^\s*(\S+)\s*->\s*(\S+)\s*$")


class ArchitectureDrift(Detector):
    """Detect imports that violate declared architecture layer rules."""

    @property
    def name(self) -> str:
        return "architecture-drift"

    @property
    def description(self) -> str:
        return "Detects imports violating declared architecture layers"

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
            logger.exception("architecture-drift failed")
            return []

    def _run(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)

        # Read architecture rules from config
        arch_config = context.config.get("architecture") or {}
        if not arch_config:
            # Also try sentinel.toml directly
            arch_config = _read_arch_config(repo_root)

        if not arch_config:
            logger.debug(
                "No [sentinel.architecture] config — "
                "architecture-drift disabled"
            )
            return []

        layers: list[str] = arch_config.get("layers", [])
        shared: list[str] = arch_config.get("shared", [])
        forbidden_raw: list[str] = arch_config.get("forbidden", [])

        if not layers and not forbidden_raw:
            return []

        # Parse forbidden rules
        forbidden = _parse_forbidden(forbidden_raw)

        # Build layer rank map (lower index = higher layer)
        layer_rank: dict[str, int] = {
            layer: idx for idx, layer in enumerate(layers)
        }
        shared_set = frozenset(shared)

        # Collect imports from Python files
        edges = _collect_import_edges(repo_root)
        if not edges:
            return []

        findings: list[Finding] = []

        for source_mod, target_mod, file_path, line_num in edges:
            # Check forbidden imports
            for from_pat, to_pat in forbidden:
                if (
                    _module_matches(source_mod, from_pat)
                    and _module_matches(target_mod, to_pat)
                ):
                    findings.append(_make_finding(
                        detector_name=self.name,
                        file_path=file_path,
                        line_num=line_num,
                        source_mod=source_mod,
                        target_mod=target_mod,
                        kind="forbidden import",
                        description=(
                            f"Import from `{source_mod}` to `{target_mod}` "
                            f"is explicitly forbidden by architecture rules "
                            f"({from_pat} -> {to_pat})."
                        ),
                        severity=Severity.HIGH,
                        confidence=0.95,
                    ))

            # Check layer violations
            if not layers:
                continue

            # Skip if target is a shared module
            if _in_shared(target_mod, shared_set):
                continue

            source_layer = _find_layer(source_mod, layer_rank)
            target_layer = _find_layer(target_mod, layer_rank)

            if source_layer is None or target_layer is None:
                continue  # module not in any declared layer

            source_rank = layer_rank[source_layer]
            target_rank = layer_rank[target_layer]

            # Lower rank = higher layer. If source is in a lower layer
            # (higher rank number) and imports from a higher layer
            # (lower rank number), that's a violation.
            if source_rank > target_rank:
                findings.append(_make_finding(
                    detector_name=self.name,
                    file_path=file_path,
                    line_num=line_num,
                    source_mod=source_mod,
                    target_mod=target_mod,
                    kind="layer violation",
                    description=(
                        f"Module `{source_mod}` (layer `{source_layer}`, "
                        f"rank {source_rank}) imports from `{target_mod}` "
                        f"(layer `{target_layer}`, rank {target_rank}). "
                        f"Lower layers should not import from higher layers."
                    ),
                    severity=Severity.MEDIUM,
                    confidence=0.90,
                ))

        return findings


# ── Import graph extraction ────────────────────────────────────────


def _collect_import_edges(
    repo_root: Path,
) -> list[tuple[str, str, str, int]]:
    """Extract (source_module, target_module, file_path, line) edges.

    Walks all Python files, parses AST, and collects import statements.
    Returns edges as (importer_dotted_path, imported_dotted_path,
    relative_file_path, line_number).
    """
    edges: list[tuple[str, str, str, int]] = []

    for py_file in sorted(repo_root.rglob("*.py")):
        if any(part in COMMON_SKIP_DIRS for part in py_file.parts):
            continue

        # Convert file path to module path
        source_mod = _path_to_module(py_file, repo_root)
        if not source_mod:
            continue

        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        rel_path = str(py_file.relative_to(repo_root))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append((
                        source_mod, alias.name, rel_path, node.lineno,
                    ))
            elif isinstance(node, ast.ImportFrom):
                resolved = _resolve_import(
                    source_mod, node.module, node.level,
                )
                if resolved:
                    edges.append((
                        source_mod, resolved, rel_path, node.lineno,
                    ))

    return edges


def _path_to_module(file_path: Path, repo_root: Path) -> str | None:
    """Convert a Python file path to a dotted module path.

    Strips common source root dirs (``src/``, ``lib/``) and converts
    path separators to dots. For ``src/myapp/core/runner.py`` returns
    ``myapp.core.runner``.
    """
    try:
        rel = file_path.relative_to(repo_root)
    except ValueError:
        return None

    parts = list(rel.parts)

    # Strip common source root dirs
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]

    if not parts:
        return None

    # Convert path parts to module parts
    module_parts: list[str] = []
    for part in parts:
        if part == "__init__.py":
            break
        if part.endswith(".py"):
            module_parts.append(part[:-3])
        else:
            module_parts.append(part)

    return ".".join(module_parts) if module_parts else None


def _resolve_import(
    source_module: str,
    module: str | None,
    level: int,
) -> str | None:
    """Resolve an import target to a full dotted module path.

    For absolute imports (``level == 0``), returns ``module`` as-is.
    For relative imports (``level > 0``), resolves against the source
    module path. E.g., ``from .foo import bar`` in ``myapp.store.db``
    resolves to ``myapp.store.foo``.
    """
    if level == 0:
        return module if module else None

    # Relative import: go up `level` packages from the source module
    parts = source_module.split(".")
    # level=1 means current package (go up 1 from module to package)
    # level=2 means parent package (go up 2), etc.
    if level > len(parts):
        return None  # can't resolve — more levels than depth

    base_parts = parts[: len(parts) - level]
    if module:
        return ".".join([*base_parts, module]) if base_parts else module
    return ".".join(base_parts) if base_parts else None


# ── Rule matching helpers ──────────────────────────────────────────


def _parse_forbidden(rules: list[str]) -> list[tuple[str, str]]:
    """Parse forbidden rules like 'a.b -> c.d' into (from, to) tuples."""
    result: list[tuple[str, str]] = []
    for rule in rules:
        m = _ARROW_RE.match(rule)
        if m:
            result.append((m.group(1), m.group(2)))
    return result


def _module_matches(module: str, pattern: str) -> bool:
    """Check if a module path starts with (or equals) a pattern prefix."""
    return module == pattern or module.startswith(pattern + ".")


def _in_shared(module: str, shared: frozenset[str]) -> bool:
    """Check if a module belongs to any shared package."""
    return any(_module_matches(module, s) for s in shared)


def _find_layer(
    module: str, layer_rank: dict[str, int],
) -> str | None:
    """Find the declared layer a module belongs to.

    Returns the most specific (longest) matching layer prefix,
    or None if not in any layer.
    """
    best: str | None = None
    for layer in layer_rank:
        if _module_matches(module, layer) and (best is None or len(layer) > len(best)):
            best = layer
    return best


def _read_arch_config(repo_root: Path) -> dict[str, Any]:
    """Read [sentinel.architecture] from sentinel.toml if present."""
    toml_path = repo_root / "sentinel.toml"
    if not toml_path.exists():
        return {}

    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return {}

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        arch: dict[str, Any] = data.get("sentinel", {}).get("architecture", {})
        return arch
    except Exception:
        logger.debug("Failed to read sentinel.toml", exc_info=True)
        return {}


def _make_finding(
    *,
    detector_name: str,
    file_path: str,
    line_num: int,
    source_mod: str,
    target_mod: str,
    kind: str,
    description: str,
    severity: Severity,
    confidence: float,
) -> Finding:
    """Create a Finding for an architecture violation."""
    return Finding(
        detector=detector_name,
        category="config-drift",
        title=f"Architecture {kind}: {source_mod} -> {target_mod}",
        description=description,
        file_path=file_path,
        line_start=line_num,
        line_end=line_num,
        severity=severity,
        confidence=confidence,
        evidence=[Evidence(
            type=EvidenceType.CODE,
            source=file_path,
            content=f"import {target_mod} (in {source_mod})",
            line_range=(line_num, line_num),
        )],
        context={
            "pattern": "architecture-drift",
            "source_module": source_mod,
            "target_module": target_mod,
            "violation_type": kind,
        },
    )
