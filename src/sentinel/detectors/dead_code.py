"""Dead code / unused exports detector.

Identifies exported symbols (functions, classes, constants) that are never
imported or referenced elsewhere in the codebase. Especially valuable after
AI-assisted rapid development where approaches get generated, tried, and
abandoned.

Supports Python and JS/TS. Uses Python's ``ast`` module for Python files
and regex-based extraction for JS/TS.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
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

# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Symbol:
    """A symbol exported from a module."""

    name: str
    module_path: str  # relative to repo root
    line: int
    kind: str  # "function", "class", "constant", "variable"


@dataclass
class _ModuleInfo:
    """Symbols defined in, and imported from, a single module."""

    path: str  # relative to repo root
    defined: list[_Symbol] = field(default_factory=list)
    # Names referenced (imported or used) from other modules
    imported_names: set[str] = field(default_factory=set)
    # Qualified module paths imported (e.g. "sentinel.models")
    imported_modules: set[str] = field(default_factory=set)
    # All names referenced within this module (for intra-file usage detection)
    internal_refs: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Skip / filter lists
# ---------------------------------------------------------------------------

# Python names that are always considered "used" (framework hooks, dunder, etc.)
_PYTHON_ALWAYS_USED: frozenset[str] = frozenset({
    # Dunder methods the runtime calls implicitly
    "__init__", "__new__", "__del__", "__repr__", "__str__",
    "__bytes__", "__format__", "__hash__", "__bool__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
    "__getattr__", "__getattribute__", "__setattr__", "__delattr__",
    "__get__", "__set__", "__delete__",
    "__call__", "__len__", "__getitem__", "__setitem__", "__delitem__",
    "__iter__", "__next__", "__contains__",
    "__enter__", "__exit__", "__aenter__", "__aexit__",
    "__add__", "__radd__", "__iadd__",
    "__sub__", "__rsub__", "__isub__",
    "__mul__", "__rmul__", "__imul__",
    "__truediv__", "__rtruediv__", "__itruediv__",
    "__floordiv__", "__rfloordiv__", "__ifloordiv__",
    "__mod__", "__rmod__", "__imod__",
    "__pow__", "__rpow__", "__ipow__",
    "__and__", "__rand__", "__iand__",
    "__or__", "__ror__", "__ior__",
    "__xor__", "__rxor__", "__ixor__",
    "__lshift__", "__rlshift__", "__ilshift__",
    "__rshift__", "__rrshift__", "__irshift__",
    "__neg__", "__pos__", "__abs__", "__invert__",
    "__int__", "__float__", "__complex__", "__index__",
    "__class_getitem__",
    "__init_subclass__", "__post_init__",
    "__set_name__",
    "__missing__",
    "__reduce__", "__reduce_ex__",
    "__copy__", "__deepcopy__",
    "__getstate__", "__setstate__",
    # Module-level dunder
    "__all__", "__version__", "__author__",
    # Common framework entry points
    "main", "app", "application", "setup", "configure",
    # PEP 517 build backend hooks
    "get_requires_for_build_sdist", "get_requires_for_build_wheel",
    "get_requires_for_build_editable", "build_sdist", "build_wheel",
    "build_editable", "prepare_metadata_for_build_wheel",
    "prepare_metadata_for_build_editable",
    # Common test fixtures and hooks
    "conftest", "pytest_configure", "pytest_collection_modifyitems",
    "pytest_addoption", "pytest_runtest_setup",
})

# JS/TS names that are always considered "used"
_JS_ALWAYS_USED: frozenset[str] = frozenset({
    "default", "App", "main", "handler", "middleware",
    "getStaticProps", "getServerSideProps", "getStaticPaths",
    "generateStaticParams", "generateMetadata",
    "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS",
    "loader", "action", "meta", "links",
    "setup", "teardown", "beforeEach", "afterEach",
    "beforeAll", "afterAll",
})

# Directories to skip (extends common set)
_EXTRA_SKIP_DIRS: frozenset[str] = frozenset({
    "migrations", "alembic", "__snapshots__",
    "generated", "proto", "vendor",
})

# File patterns to skip
_SKIP_FILE_PATTERNS: frozenset[str] = frozenset({
    "conftest.py",
    "setup.py",
    "__init__.py",  # __init__.py is often re-export only
})


# ---------------------------------------------------------------------------
# Python: ast-based symbol extraction
# ---------------------------------------------------------------------------

def _parse_python_module(path: Path, rel_path: str) -> _ModuleInfo | None:
    """Parse a Python file and return defined symbols and imports."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None

    info = _ModuleInfo(path=rel_path)

    # Check for __all__ — if defined, only those names are "exported"
    all_names: set[str] | None = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    all_names = _extract_all_names(node.value)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            info.defined.append(_Symbol(
                name=node.name,
                module_path=rel_path,
                line=node.lineno,
                kind="function",
            ))
        elif isinstance(node, ast.ClassDef):
            info.defined.append(_Symbol(
                name=node.name,
                module_path=rel_path,
                line=node.lineno,
                kind="class",
            ))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    info.defined.append(_Symbol(
                        name=target.id,
                        module_path=rel_path,
                        line=node.lineno,
                        kind="constant",
                    ))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                used_name = alias.asname if alias.asname else alias.name
                info.imported_names.add(used_name)
                # `import X` means all symbols in X are potentially accessed
                info.imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # `from X import y` — only y is used, not all of X's symbols.
            # Do NOT add node.module to imported_modules here.
            for alias in node.names:
                used_name = alias.asname if alias.asname else alias.name
                info.imported_names.add(used_name)

    # If __all__ is defined, filter exported symbols to only __all__ members
    if all_names is not None:
        info.defined = [s for s in info.defined if s.name in all_names]

    # Collect all names referenced within the module (for intra-file usage).
    # Walk the full AST, not just top-level children, to find references in
    # function bodies, class methods, decorators, default arguments, etc.
    defined_names = {s.name for s in info.defined}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in defined_names:
            # Don't count the definition site itself — only references.
            # Definition sites are Assign targets and FunctionDef/ClassDef names,
            # which appear as Store context.  References are Load context.
            if isinstance(node.ctx, ast.Load):
                info.internal_refs.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in defined_names:
            # Catches patterns like ClassName.method or MODULE_CONST.attr
            info.internal_refs.add(node.value.id)

    return info


def _extract_all_names(node: ast.expr) -> set[str] | None:
    """Extract string values from an __all__ assignment (list or tuple)."""
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    names: set[str] = set()
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            names.add(elt.value)
    return names


# ---------------------------------------------------------------------------
# JS/TS: regex-based symbol extraction
# ---------------------------------------------------------------------------

# Match: export function name(...)
# Match: export async function name(...)
# Match: export class Name
# Match: export const NAME = ...
# Match: export let name = ...
# Match: export var name = ...
# Match: export default function name(...)
# Match: export default class Name
_JS_EXPORT_PATTERN = re.compile(
    r"^export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function\*?\s+|class\s+|const\s+|let\s+|var\s+)"
    r"(\w+)",
    re.MULTILINE,
)

# Match: export { name1, name2 as alias }
_JS_NAMED_EXPORT_PATTERN = re.compile(
    r"^export\s*\{([^}]+)\}",
    re.MULTILINE,
)

# Match: import { name1, name2 } from './module'
# Match: import name from './module'
# Match: import * as name from './module'
_JS_IMPORT_PATTERN = re.compile(
    r"""import\s+(?:"""
    r"""\{([^}]+)\}"""  # named imports
    r"""|(\w+)"""  # default import
    r"""|(\*\s+as\s+\w+)"""  # namespace import
    r""")\s+from\s+['"]([^'"]+)['"]""",
    re.MULTILINE,
)

# Match: require('./module')
_JS_REQUIRE_PATTERN = re.compile(
    r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)

# Match: dynamic import('module') — counts as usage
_JS_DYNAMIC_IMPORT_PATTERN = re.compile(
    r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)

# Auto-generated file detection
_AUTO_GENERATED_PATTERN = re.compile(
    r"(?:auto[- ]?generated|do not edit|generated by)",
    re.IGNORECASE,
)


def _parse_js_module(path: Path, rel_path: str) -> _ModuleInfo | None:
    """Parse a JS/TS file and return exported symbols and imports."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Skip auto-generated files — their exports are consumed dynamically
    header = source[:500]
    if _AUTO_GENERATED_PATTERN.search(header):
        return None

    info = _ModuleInfo(path=rel_path)

    # Extract exported symbols
    for match in _JS_EXPORT_PATTERN.finditer(source):
        name = match.group(1)
        line = source[:match.start()].count("\n") + 1
        kind = "class" if "class " in match.group() else "function"
        if re.search(r"\b(?:const|let|var)\b", match.group()):
            kind = "constant" if name.isupper() else "variable"
        info.defined.append(_Symbol(
            name=name, module_path=rel_path, line=line, kind=kind,
        ))

    # Extract named exports: export { name1, name2 }
    for match in _JS_NAMED_EXPORT_PATTERN.finditer(source):
        names_str = match.group(1)
        line = source[:match.start()].count("\n") + 1
        for name_part in names_str.split(","):
            name_part = name_part.strip()
            if " as " in name_part:
                name_part = name_part.split(" as ")[1].strip()
            if name_part:
                info.defined.append(_Symbol(
                    name=name_part, module_path=rel_path, line=line, kind="variable",
                ))

    # Extract imports (to build usage graph)
    for match in _JS_IMPORT_PATTERN.finditer(source):
        named = match.group(1)
        default_name = match.group(2)
        module_path = match.group(4)
        if named:
            for part in named.split(","):
                part = part.strip()
                if " as " in part:
                    part = part.split(" as ")[1].strip()
                if part:
                    info.imported_names.add(part)
        if default_name:
            info.imported_names.add(default_name)
        if module_path:
            info.imported_modules.add(module_path)

    for match in _JS_REQUIRE_PATTERN.finditer(source):
        info.imported_modules.add(match.group(1))

    # Track dynamic import() calls as module usage
    for match in _JS_DYNAMIC_IMPORT_PATTERN.finditer(source):
        info.imported_modules.add(match.group(1))

    return info


# ---------------------------------------------------------------------------
# Cross-referencing logic
# ---------------------------------------------------------------------------

def _python_module_path(rel_path: str) -> str:
    """Convert a relative file path to a Python dotted module path.

    e.g. ``src/sentinel/models.py`` → ``sentinel.models``
    """
    parts = Path(rel_path).with_suffix("").parts
    # Strip leading 'src' if present
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def _is_test_file(rel_path: str) -> bool:
    """Check if a file path is a test file."""
    name = Path(rel_path).name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.ts")
        or name.endswith(".test.js")
        or name.endswith(".test.tsx")
        or name.endswith(".test.jsx")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.js")
        or name.endswith(".spec.tsx")
        or name.endswith(".spec.jsx")
    )


def _should_skip_dir(dirname: str) -> bool:
    return dirname in COMMON_SKIP_DIRS or dirname in _EXTRA_SKIP_DIRS


def _collect_python_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Collect all Python files with their relative paths."""
    files: list[tuple[Path, str]] = []
    for py_file in repo_root.rglob("*.py"):
        if any(_should_skip_dir(p) for p in py_file.relative_to(repo_root).parts):
            continue
        rel = str(py_file.relative_to(repo_root))
        files.append((py_file, rel))
    return files


def _collect_js_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Collect all JS/TS files with their relative paths."""
    files: list[tuple[Path, str]] = []
    extensions = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
    for ext in extensions:
        for js_file in repo_root.rglob(f"*{ext}"):
            if any(_should_skip_dir(p) for p in js_file.relative_to(repo_root).parts):
                continue
            rel = str(js_file.relative_to(repo_root))
            files.append((js_file, rel))
    return files


def _find_unused_python_symbols(
    modules: list[_ModuleInfo],
) -> list[_Symbol]:
    """Cross-reference Python module definitions against imports.

    A symbol is "unused" if:
    - It's not in _PYTHON_ALWAYS_USED
    - It starts with a letter (not underscore-prefixed private)
    - Its name is never imported by any other module
    - Its containing module is never wildcard-imported
    """
    # Build a global set of all imported names and modules
    all_imported_names: set[str] = set()
    all_imported_modules: set[str] = set()
    for mod in modules:
        all_imported_names.update(mod.imported_names)
        all_imported_modules.update(mod.imported_modules)

    unused: list[_Symbol] = []
    for mod in modules:
        mod_dotted = _python_module_path(mod.path)
        for symbol in mod.defined:
            # Skip private symbols (underscore-prefixed)
            if symbol.name.startswith("_"):
                continue
            # Skip always-used names
            if symbol.name in _PYTHON_ALWAYS_USED:
                continue
            # Skip if the symbol is referenced within its own module
            if symbol.name in mod.internal_refs:
                continue
            # Skip if the name appears as an import in any other module
            if symbol.name in all_imported_names:
                continue
            # Skip if the module itself is imported (could be accessed as mod.symbol)
            if mod_dotted in all_imported_modules:
                continue
            # Skip if any parent package is imported
            parts = mod_dotted.split(".")
            if any(
                ".".join(parts[:i]) in all_imported_modules
                for i in range(1, len(parts))
            ):
                continue
            unused.append(symbol)

    return unused


def _find_unused_js_symbols(
    modules: list[_ModuleInfo],
) -> list[_Symbol]:
    """Cross-reference JS/TS module exports against imports."""
    all_imported_names: set[str] = set()
    all_imported_modules: set[str] = set()
    for mod in modules:
        all_imported_names.update(mod.imported_names)
        all_imported_modules.update(mod.imported_modules)

    unused: list[_Symbol] = []
    for mod in modules:
        for symbol in mod.defined:
            if symbol.name in _JS_ALWAYS_USED:
                continue
            if symbol.name in all_imported_names:
                continue
            unused.append(symbol)

    return unused


# ---------------------------------------------------------------------------
# Detector class
# ---------------------------------------------------------------------------

class DeadCodeDetector(Detector):
    """Detect exported symbols that are never imported elsewhere."""

    @property
    def name(self) -> str:
        return "dead-code"

    @property
    def description(self) -> str:
        return (
            "Identifies exported functions, classes, and constants that are "
            "never imported elsewhere in the codebase."
        )

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.HEURISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._detect_impl(context)
        except Exception:
            logger.exception("dead-code detector failed")
            return []

    def _detect_impl(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)
        findings: list[Finding] = []

        # --- Python ---
        py_files = _collect_python_files(repo_root)

        # Parse all files once
        all_py_modules: list[_ModuleInfo] = []
        for path, rel in py_files:
            info = _parse_python_module(path, rel)
            if info:
                if Path(rel).name in _SKIP_FILE_PATTERNS:
                    info.defined = []  # Don't flag these as unused
                all_py_modules.append(info)

        # Separate: definitions come from non-test, non-skip files.
        # Imports from ALL files (including tests) count as "used".
        reportable_modules = [
            m for m in all_py_modules
            if m.defined and not _is_test_file(m.path)
        ]
        unused_py = _find_unused_python_symbols(
            # All modules for import tracking, but only reportable ones have definitions
            [
                _ModuleInfo(
                    path=m.path,
                    defined=m.defined if m in reportable_modules else [],
                    imported_names=m.imported_names,
                    imported_modules=m.imported_modules,
                    internal_refs=m.internal_refs,
                )
                for m in all_py_modules
            ]
        )

        for sym in unused_py:
            findings.append(Finding(
                detector=self.name,
                category="code-quality",
                severity=Severity.LOW,
                confidence=0.7,
                title=f"Unused {sym.kind}: {sym.name}",
                description=(
                    f"{sym.kind.title()} `{sym.name}` is defined in "
                    f"`{sym.module_path}` but never imported or referenced "
                    f"elsewhere in the codebase."
                ),
                file_path=sym.module_path,
                line_start=sym.line,
                evidence=[Evidence(
                    type=EvidenceType.CODE,
                    source=sym.module_path,
                    content=f"{sym.kind} {sym.name} (line {sym.line})",
                    line_range=(sym.line, sym.line),
                )],
            ))

        # --- JS/TS ---
        js_files = _collect_js_files(repo_root)
        js_modules: list[_ModuleInfo] = []
        for path, rel in js_files:
            info = _parse_js_module(path, rel)
            if info:
                js_modules.append(info)

        reportable_js = [
            m for m in js_modules if m.defined and not _is_test_file(m.path)
        ]
        unused_js = _find_unused_js_symbols(
            [
                _ModuleInfo(
                    path=m.path,
                    defined=m.defined if m in reportable_js else [],
                    imported_names=m.imported_names,
                    imported_modules=m.imported_modules,
                )
                for m in js_modules
            ]
        )

        for sym in unused_js:
            findings.append(Finding(
                detector=self.name,
                category="code-quality",
                severity=Severity.LOW,
                confidence=0.6,
                title=f"Unused export: {sym.name}",
                description=(
                    f"Exported {sym.kind} `{sym.name}` in "
                    f"`{sym.module_path}` is never imported elsewhere."
                ),
                file_path=sym.module_path,
                line_start=sym.line,
                evidence=[Evidence(
                    type=EvidenceType.CODE,
                    source=sym.module_path,
                    content=f"export {sym.kind} {sym.name} (line {sym.line})",
                    line_range=(sym.line, sym.line),
                )],
            ))

        return findings
