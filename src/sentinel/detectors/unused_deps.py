"""Unused dependencies detector.

Compares declared dependencies (pyproject.toml, package.json) against
actual imports in source code. Flags packages that are declared but
never imported — different from dep-audit which checks for CVEs.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import tomllib
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

# Known package-name → import-name mappings where they differ.
# Keys are normalized (lowercase, hyphens→underscores).
_PACKAGE_TO_IMPORT: dict[str, str | list[str]] = {
    "pillow": "PIL",
    "python_dateutil": "dateutil",
    "scikit_learn": "sklearn",
    "beautifulsoup4": "bs4",
    "pyyaml": "yaml",
    "pymysql": "pymysql",
    "python_dotenv": "dotenv",
    "attrs": "attr",
    "pyjwt": "jwt",
    "python_multipart": "multipart",
    "msgpack_python": "msgpack",
    "ruamel_yaml": "ruamel",
    "markupsafe": "markupsafe",
    "python_jose": "jose",
    "opencv_python": "cv2",
    "opencv_python_headless": "cv2",
    "protobuf": "google.protobuf",
    "google_protobuf": "google.protobuf",
}

# Packages that are typically runtime/tool deps, not imported in source.
_TOOL_PACKAGES: frozenset[str] = frozenset({
    # Build tools
    "setuptools", "wheel", "pip", "build", "flit", "hatch", "hatchling",
    "poetry", "poetry_core", "maturin",
    # Type stubs
    "types_requests", "types_pyyaml", "types_toml", "types_setuptools",
    "mypy_extensions",
    # Testing tools (invoked via CLI, not imported in prod)
    "pytest", "pytest_cov", "pytest_xdist", "pytest_asyncio",
    "pytest_mock", "pytest_tmp_files", "coverage", "tox", "nox",
    # Linters/formatters
    "ruff", "black", "isort", "flake8", "pylint", "mypy", "pyright",
    # Audit tools (invoked via CLI)
    "pip_audit", "safety", "bandit",
    # Dev utilities
    "pre_commit", "ipython", "ipdb", "debugpy",
})

# JS packages that are build-time tools or plugins, not imported in source
_JS_TOOL_PACKAGES: frozenset[str] = frozenset({
    "typescript", "eslint", "prettier", "jest", "vitest", "mocha",
    "webpack", "vite", "rollup", "esbuild", "parcel", "turbo",
    "@types/node", "@types/react", "@types/jest",
    "tsconfig-paths", "ts-node", "nodemon", "concurrently",
})


def _normalize_package_name(name: str) -> str:
    """Normalize a package name: lowercase, hyphens/dots to underscores."""
    return re.sub(r"[-.]", "_", name.lower())


def _strip_version(spec: str) -> str:
    """Strip version specifiers from a dependency string.

    Examples: 'requests>=2.28' → 'requests', 'click[dev]' → 'click'
    """
    # Remove extras like [dev]
    name = re.split(r"[\[;><=!~\s]", spec.strip())[0]
    return name.strip()


def _expected_import_names(package_name: str) -> list[str]:
    """Return possible import names for a package.

    Returns a list because some packages can be imported multiple ways.
    Since we collect imports at the top-level (e.g. 'google' from
    'import google.protobuf'), we also return the top-level component
    of dotted mappings.
    """
    normalized = _normalize_package_name(package_name)

    # Check known mappings
    mapped = _PACKAGE_TO_IMPORT.get(normalized)
    if mapped:
        names_raw = mapped if isinstance(mapped, list) else [mapped]
        names: list[str] = []
        for m in names_raw:
            lowered = m.lower()
            names.append(lowered)
            # Also add the top-level package for dotted names
            top = lowered.split(".")[0]
            if top != lowered:
                names.append(top)
        return names

    # Default: the normalized name itself (hyphens → underscores)
    return [normalized]


class UnusedDeps(Detector):
    """Detect declared dependencies that are never imported in source code."""

    @property
    def name(self) -> str:
        return "unused-deps"

    @property
    def description(self) -> str:
        return "Flags declared dependencies not imported in source code"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["dependency"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._run(context)
        except Exception:
            logger.exception("unused-deps failed")
            return []

    def _run(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)
        findings: list[Finding] = []

        # Python dependencies
        py_deps = self._get_python_deps(repo_root)
        if py_deps:
            py_imports = self._collect_python_imports(repo_root, context)
            findings.extend(
                self._check_unused(py_deps, py_imports, repo_root, "python")
            )

        # JS/TS dependencies
        js_deps = self._get_js_deps(repo_root)
        if js_deps:
            js_imports = self._collect_js_imports(repo_root, context)
            findings.extend(
                self._check_unused(js_deps, js_imports, repo_root, "javascript")
            )

        return findings

    def _check_unused(
        self,
        declared: dict[str, str],
        imported: set[str],
        repo_root: Path,
        lang: str,
    ) -> list[Finding]:
        """Compare declared deps against imports and produce findings."""
        findings: list[Finding] = []

        for package_name, source_file in declared.items():
            normalized = _normalize_package_name(package_name)

            # Skip known tool packages
            if lang == "python" and normalized in _TOOL_PACKAGES:
                continue
            if lang == "javascript" and package_name in _JS_TOOL_PACKAGES:
                continue

            # Check if any expected import name appears in the import set
            expected = _expected_import_names(package_name)
            if any(imp in imported for imp in expected):
                continue

            # Also check by normalized name directly (handles most cases)
            if normalized in imported:
                continue

            # For JS, check raw package name (imports preserve hyphens/scopes)
            if lang == "javascript" and package_name in imported:
                continue

            findings.append(Finding(
                detector=self.name,
                category="dependency",
                title=f"Unused dependency: {package_name}",
                description=(
                    f"Package '{package_name}' is declared in {source_file} "
                    f"but no matching import was found in {lang} source files."
                ),
                file_path=source_file,
                severity=Severity.LOW,
                confidence=0.80,
                evidence=[Evidence(
                    type=EvidenceType.CONFIG,
                    source=source_file,
                    content=f"Declared: {package_name}\nExpected imports: {', '.join(expected)}",
                )],
            ))

        return findings

    # ── Python dep extraction ────────────────────────────────────────

    def _get_python_deps(self, repo_root: Path) -> dict[str, str]:
        """Get declared Python dependencies. Returns {package_name: source_file}."""
        deps: dict[str, str] = {}

        pyproject = repo_root / "pyproject.toml"
        if pyproject.exists():
            try:
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                return deps

            # PEP 621
            for spec in data.get("project", {}).get("dependencies", []):
                name = _strip_version(spec)
                if name:
                    deps[name] = "pyproject.toml"

            # Optional dependency groups (PEP 621)
            for group_deps in data.get("project", {}).get("optional-dependencies", {}).values():
                for spec in group_deps:
                    name = _strip_version(spec)
                    if name:
                        deps[name] = "pyproject.toml"

            # Poetry
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for name in poetry_deps:
                if name.lower() != "python":
                    deps[name] = "pyproject.toml"

            # Poetry dev groups
            for group_data in data.get("tool", {}).get("poetry", {}).get("group", {}).values():
                for name in group_data.get("dependencies", {}):
                    deps[name] = "pyproject.toml"

        # requirements.txt
        req_file = repo_root / "requirements.txt"
        if req_file.exists():
            try:
                for line in req_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "-")):
                        name = _strip_version(line)
                        if name and name not in deps:
                            deps[name] = "requirements.txt"
            except OSError:
                pass

        return deps

    # ── JS dep extraction ────────────────────────────────────────────

    def _get_js_deps(self, repo_root: Path) -> dict[str, str]:
        """Get declared JS/TS dependencies from package.json."""
        deps: dict[str, str] = {}
        pkg_json = repo_root / "package.json"
        if not pkg_json.exists():
            return deps

        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return deps

        for section in ("dependencies", "devDependencies"):
            for name in data.get(section, {}):
                deps[name] = "package.json"

        return deps

    # ── Python import collection ─────────────────────────────────────

    def _collect_python_imports(
        self, repo_root: Path, context: DetectorContext,
    ) -> set[str]:
        """Collect all top-level import names from Python source files."""
        imports: set[str] = set()

        files = self._get_python_files(repo_root, context)
        for py_file in files:
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_file))
            except (SyntaxError, OSError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Take the top-level package: 'import foo.bar' → 'foo'
                        top = alias.name.split(".")[0].lower()
                        imports.add(top)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0].lower()
                    imports.add(top)

        return imports

    def _get_python_files(
        self, repo_root: Path, context: DetectorContext,
    ) -> list[Path]:
        """Get Python files to scan for imports."""
        if context.target_paths:
            files: list[Path] = []
            for tp in context.target_paths:
                p = Path(tp)
                if not p.is_absolute():
                    p = repo_root / p
                if p.is_file() and p.suffix == ".py":
                    files.append(p)
                elif p.is_dir():
                    files.extend(self._walk_py_files(p))
            return files

        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            return [
                repo_root / f for f in context.changed_files
                if f.endswith(".py") and (repo_root / f).exists()
            ]

        return self._walk_py_files(repo_root)

    @staticmethod
    def _walk_py_files(root: Path) -> list[Path]:
        """Walk directory for .py files, skipping common dirs."""
        files: list[Path] = []
        for path in root.rglob("*.py"):
            if any(part in COMMON_SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
        return files

    # ── JS import collection ─────────────────────────────────────────

    def _collect_js_imports(
        self, repo_root: Path, context: DetectorContext,
    ) -> set[str]:
        """Collect all import/require names from JS/TS source files."""
        imports: set[str] = set()

        # Patterns for: import X from 'pkg', require('pkg'), import('pkg')
        import_re = re.compile(
            r"""(?:from\s+['"]([^'"]+)['"]"""  # from 'pkg'
            r"""|require\(\s*['"]([^'"]+)['"]\s*\)"""  # require('pkg')
            r"""|import\(\s*['"]([^'"]+)['"]\s*\))""",  # import('pkg')
            re.MULTILINE,
        )

        files = self._get_js_files(repo_root, context)
        for js_file in files:
            try:
                source = js_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in import_re.finditer(source):
                raw = m.group(1) or m.group(2) or m.group(3)
                if raw and not raw.startswith("."):
                    # Scoped packages: @scope/pkg → @scope/pkg
                    # Regular packages: pkg/sub → pkg
                    if raw.startswith("@"):
                        parts = raw.split("/")
                        name = "/".join(parts[:2]) if len(parts) >= 2 else raw
                    else:
                        name = raw.split("/")[0]
                    imports.add(name)

        return imports

    def _get_js_files(
        self, repo_root: Path, context: DetectorContext,
    ) -> list[Path]:
        """Get JS/TS files to scan for imports."""
        exts = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

        if context.target_paths:
            files: list[Path] = []
            for tp in context.target_paths:
                p = Path(tp)
                if not p.is_absolute():
                    p = repo_root / p
                if p.is_file() and p.suffix in exts:
                    files.append(p)
                elif p.is_dir():
                    files.extend(self._walk_js_files(p, exts))
            return files

        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            return [
                repo_root / f for f in context.changed_files
                if any(f.endswith(ext) for ext in exts) and (repo_root / f).exists()
            ]

        return self._walk_js_files(repo_root, exts)

    @staticmethod
    def _walk_js_files(root: Path, exts: set[str]) -> list[Path]:
        """Walk directory for JS/TS files, skipping common dirs."""
        files: list[Path] = []
        for ext in exts:
            for path in root.rglob(f"*{ext}"):
                if any(part in COMMON_SKIP_DIRS for part in path.parts):
                    continue
                files.append(path)
        return files
