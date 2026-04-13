"""Language-agnostic source code extraction for LLM-assisted detectors.

Provides a unified interface for extracting functions, classes, signatures,
docstrings, and imports from source files in multiple languages.

Backends:
- Python: uses the built-in ``ast`` module (zero dependencies)
- JS/TS: uses tree-sitter (optional dependency)
- Fallback: regex-based extraction when tree-sitter is unavailable

The tree-sitter packages are optional; when absent, JS/TS extraction
degrades gracefully to regex-based heuristics.
"""

from __future__ import annotations

import ast
import logging
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Language detection ─────────────────────────────────────────────

_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
}

# Languages supported for AST extraction (python always; js/ts when tree-sitter available)
SUPPORTED_LANGUAGES = frozenset({"python", "javascript", "typescript"})


def detect_language(file_path: str | Path) -> str | None:
    """Detect programming language from file extension.

    Returns a language identifier string (``"python"``, ``"javascript"``,
    ``"typescript"``) or ``None`` for unsupported extensions.
    """
    suffix = Path(file_path).suffix.lower()
    return _EXTENSION_MAP.get(suffix)


# ── Source file extensions by language ─────────────────────────────

# Implementation file globs (non-test)
SOURCE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "python": ("*.py",),
    "javascript": ("*.js", "*.mjs", "*.cjs", "*.jsx"),
    "typescript": ("*.ts", "*.mts", "*.cts", "*.tsx"),
}

# Test file patterns by language
TEST_FILE_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"^test_\w+\.py$|^\w+_test\.py$"),
    "javascript": re.compile(
        r"^.+\.(?:test|spec)\.(?:js|jsx|mjs|cjs)$|^.+\.test\.(?:js|jsx|mjs|cjs)$"
    ),
    "typescript": re.compile(
        r"^.+\.(?:test|spec)\.(?:ts|tsx|mts|cts)$|^.+\.test\.(?:ts|tsx|mts|cts)$"
    ),
}

# Directories that usually contain tests (for JS/TS)
TEST_DIRS = frozenset({"__tests__", "__test__", "tests", "test", "spec"})


def is_test_file(file_path: str | Path, language: str | None = None) -> bool:
    """Check whether a file is a test file based on naming conventions."""
    p = Path(file_path)
    lang = language or detect_language(p)
    if lang and lang in TEST_FILE_PATTERNS and TEST_FILE_PATTERNS[lang].match(p.name):
        return True
    # Check parent directory
    return any(part in TEST_DIRS for part in p.parts)


def impl_name_from_test(test_filename: str, language: str) -> str | None:
    """Derive implementation filename from test filename.

    Python: test_config.py → config.py, config_test.py → config.py
    JS/TS: config.test.ts → config.ts, config.spec.js → config.js
    """
    if language == "python":
        if test_filename.startswith("test_"):
            return test_filename[5:]
        suffixes = ("_test.py",)
        for s in suffixes:
            if test_filename.endswith(s):
                return test_filename[: -len(s)] + ".py"
        return None

    if language in ("javascript", "typescript"):
        # foo.test.ts → foo.ts, foo.spec.js → foo.js
        for marker in (".test.", ".spec."):
            idx = test_filename.find(marker)
            if idx >= 0:
                ext = test_filename[idx + len(marker) - 1 :]  # e.g. ".ts"
                return test_filename[:idx] + ext
        return None

    return None


# ── Data structures ────────────────────────────────────────────────


@dataclass(frozen=True)
class FunctionInfo:
    """Extracted function or method information."""

    name: str
    body: str  # Full text of the function (including def/function line)
    signature: str  # Just the declaration line(s), no body
    line_start: int  # 1-indexed
    line_end: int  # 1-indexed inclusive
    docstring: str | None = None
    is_method: bool = False
    class_name: str | None = None


@dataclass(frozen=True)
class ClassInfo:
    """Extracted class information."""

    name: str
    body: str  # Full class text
    signature: str  # Class line + docstring + method sigs
    line_start: int
    line_end: int
    docstring: str | None = None
    methods: tuple[FunctionInfo, ...] = ()


@dataclass(frozen=True)
class DocstringPair:
    """A docstring paired with its code body (for drift detection)."""

    name: str
    docstring: str
    code: str  # Body code without the docstring
    line_start: int
    docstring_end: int
    code_start: int
    code_end: int


@dataclass(frozen=True)
class ImportInfo:
    """An import statement."""

    module: str  # Module path (e.g. "sentinel.config" or "./other-module")
    names: tuple[str, ...] = ()  # Imported names (e.g. ("Config", "load"))
    line: int = 1
    is_type_only: bool = False  # TypeScript "import type"


# ── Public extraction interface ────────────────────────────────────


def extract_functions(source: str, language: str) -> list[FunctionInfo]:
    """Extract function definitions from source code.

    Returns all top-level functions and class methods.
    """
    if language == "python":
        return _py_extract_functions(source)
    if language in ("javascript", "typescript"):
        return _ts_extract_functions(source, language)
    return []


def extract_classes(source: str, language: str) -> list[ClassInfo]:
    """Extract class definitions from source code."""
    if language == "python":
        return _py_extract_classes(source)
    if language in ("javascript", "typescript"):
        return _ts_extract_classes(source, language)
    return []


def extract_signatures(source: str, language: str) -> str | None:
    """Extract compact function/class signatures (without bodies).

    Used by semantic-drift for comparing docs against code structure.
    """
    if language == "python":
        return _py_extract_signatures(source)
    if language in ("javascript", "typescript"):
        return _ts_extract_signatures(source, language)
    return None


def extract_docstring_pairs(
    source: str, language: str, *, min_docstring_chars: int = 30,
) -> list[DocstringPair]:
    """Extract (docstring, code body) pairs for drift detection.

    Used by inline-comment-drift and intent-comparison.
    """
    if language == "python":
        return _py_extract_docstring_pairs(source, min_docstring_chars)
    if language in ("javascript", "typescript"):
        return _ts_extract_docstring_pairs(source, language, min_docstring_chars)
    return []


def extract_imports(source: str, language: str) -> list[ImportInfo]:
    """Extract import statements from source code."""
    if language == "python":
        return _py_extract_imports(source)
    if language in ("javascript", "typescript"):
        return _ts_extract_imports(source, language)
    return []


# ── Python AST backend ─────────────────────────────────────────────


def _py_extract_functions(source: str) -> list[FunctionInfo]:
    """Extract functions from Python source using the ast module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.split("\n")
    functions: list[FunctionInfo] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = _py_function_info(node, lines)
            if fn:
                functions.append(fn)
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn = _py_function_info(child, lines, class_name=node.name)
                    if fn:
                        functions.append(fn)

    return functions


def _py_function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
    *,
    class_name: str | None = None,
) -> FunctionInfo | None:
    """Build FunctionInfo from a Python AST function node."""
    start = node.lineno - 1  # 0-indexed
    end = node.end_lineno  # exclusive in ast, inclusive in our model
    if start < 0 or end is None or end > len(lines):
        return None

    body = "\n".join(lines[start:end])

    # Signature: def line(s) up to the first body node
    sig_end = start + 1
    if node.body:
        sig_end = node.body[0].lineno - 1
    sig_lines = lines[start : min(sig_end, start + 5)]
    signature = "\n".join(s.rstrip() for s in sig_lines)

    docstring = ast.get_docstring(node, clean=True)

    return FunctionInfo(
        name=node.name,
        body=body,
        signature=signature,
        line_start=node.lineno,
        line_end=end,
        docstring=docstring,
        is_method=class_name is not None,
        class_name=class_name,
    )


def _py_extract_classes(source: str) -> list[ClassInfo]:
    """Extract classes from Python source using the ast module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.split("\n")
    classes: list[ClassInfo] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            cls = _py_class_info(node, lines)
            if cls:
                classes.append(cls)

    return classes


def _py_class_info(node: ast.ClassDef, lines: list[str]) -> ClassInfo | None:
    """Build ClassInfo from a Python AST class node."""
    start = node.lineno - 1
    end = node.end_lineno
    if start < 0 or end is None or end > len(lines):
        return None

    body = "\n".join(lines[start:end])
    class_line = lines[start].rstrip()
    docstring = ast.get_docstring(node, clean=True)

    # Build signature: class line + docstring + method def lines
    sig_parts = [class_line]
    if docstring:
        trunc = docstring[:200] + "..." if len(docstring) > 200 else docstring
        sig_parts.append(f'    """{trunc}"""')
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.lineno - 1 < len(lines):
            sig_parts.append(f"    {lines[item.lineno - 1].strip()}")

    # Extract methods
    methods: list[FunctionInfo] = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = _py_function_info(item, lines, class_name=node.name)
            if fn:
                methods.append(fn)

    return ClassInfo(
        name=node.name,
        body=body,
        signature="\n".join(sig_parts),
        line_start=node.lineno,
        line_end=end,
        docstring=docstring,
        methods=tuple(methods),
    )


def _py_extract_signatures(source: str) -> str | None:
    """Extract compact signatures from Python source (for semantic-drift)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        lines = source.split("\n")
        return "\n".join(lines[:80])

    parts: list[str] = []
    lines = source.split("\n")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _py_format_function_sig(node, lines)
            if sig:
                parts.append(sig)
        elif isinstance(node, ast.ClassDef):
            sig = _py_format_class_sig(node, lines)
            if sig:
                parts.append(sig)

    if not parts:
        return "\n".join(lines[:80])

    return "\n\n".join(parts)


def _py_format_function_sig(
    node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str],
) -> str | None:
    """Format a Python function signature with docstring."""
    start = node.lineno - 1
    end = start + 1
    if node.body:
        end = node.body[0].lineno - 1
    sig_lines = lines[start : min(end, start + 5)]
    sig = "\n".join(s.rstrip() for s in sig_lines)

    docstring = ast.get_docstring(node)
    if docstring:
        if len(docstring) > 200:
            docstring = docstring[:200] + "..."
        return f'{sig}\n    """{docstring}"""'
    return sig


def _py_format_class_sig(node: ast.ClassDef, lines: list[str]) -> str | None:
    """Format a Python class signature with docstring and method sigs."""
    start = node.lineno - 1
    if start >= len(lines):
        return None
    class_line = lines[start].rstrip()
    parts = [class_line]

    docstring = ast.get_docstring(node)
    if docstring:
        if len(docstring) > 200:
            docstring = docstring[:200] + "..."
        parts.append(f'    """{docstring}"""')

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.lineno - 1 < len(lines):
            method_line = lines[item.lineno - 1].rstrip()
            parts.append(f"    {method_line.strip()}")

    return "\n".join(parts)


def _py_extract_docstring_pairs(
    source: str, min_chars: int,
) -> list[DocstringPair]:
    """Extract (docstring, code body) pairs from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    pairs: list[DocstringPair] = []

    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue

        docstring = ast.get_docstring(node, clean=True)
        if not docstring or len(docstring) < min_chars:
            continue

        body_nodes = node.body[1:]  # skip docstring node
        if not body_nodes:
            continue

        line_start = node.lineno
        end_lineno = node.end_lineno or node.lineno

        ds_node = node.body[0]
        docstring_end = ds_node.end_lineno or ds_node.lineno

        code_start = body_nodes[0].lineno
        code_end = end_lineno

        if code_start <= code_end <= len(lines):
            body_text = "\n".join(lines[code_start - 1 : code_end])
            body_text = textwrap.dedent(body_text)
        else:
            continue

        pairs.append(DocstringPair(
            name=node.name,
            docstring=docstring,
            code=body_text,
            line_start=line_start,
            docstring_end=docstring_end,
            code_start=code_start,
            code_end=code_end,
        ))

    return pairs


def _py_extract_imports(source: str) -> list[ImportInfo]:
    """Extract imports from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports: list[ImportInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    names=(),
                    line=node.lineno,
                ))
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = tuple(alias.name for alias in node.names)
            imports.append(ImportInfo(
                module=node.module,
                names=names,
                line=node.lineno,
            ))

    return imports


# ── Tree-sitter backend (JS/TS) ───────────────────────────────────

_HAS_TREE_SITTER = False
_JS_PARSER: Any = None
_TS_PARSER: Any = None

try:
    from tree_sitter import Language as TSLanguage
    from tree_sitter import Parser as TSParser

    try:
        import tree_sitter_javascript as _tsjs

        _JS_PARSER = TSParser(TSLanguage(_tsjs.language()))
    except ImportError:
        pass

    try:
        import tree_sitter_typescript as _tsts

        _TS_PARSER = TSParser(TSLanguage(_tsts.language_typescript()))
    except ImportError:
        pass

    _HAS_TREE_SITTER = _JS_PARSER is not None or _TS_PARSER is not None
except ImportError:
    pass


def has_tree_sitter() -> bool:
    """Return whether tree-sitter is available for JS/TS parsing."""
    return _HAS_TREE_SITTER


def _ts_get_parser(language: str) -> Any | None:
    """Get the tree-sitter parser for a language."""
    if language == "javascript":
        return _JS_PARSER
    if language == "typescript":
        return _TS_PARSER
    return None


# ── Tree-sitter helpers ────────────────────────────────────────────


def _ts_node_text(node: Any) -> str:
    """Get the text content of a tree-sitter node as a string."""
    return node.text.decode("utf-8") if node.text else ""


def _ts_node_lines(node: Any) -> tuple[int, int]:
    """Get 1-indexed (start, end) line numbers for a tree-sitter node."""
    return (node.start_point[0] + 1, node.end_point[0] + 1)


def _ts_find_jsdoc(node: Any, parent: Any) -> str | None:
    """Find JSDoc comment preceding a node in the parent's children.

    JSDoc comments (``/** ... */``) are sibling nodes, not children
    of the declaration.
    """
    children = parent.children
    idx = None
    for i, child in enumerate(children):
        if child.id == node.id:
            idx = i
            break
    if idx is None or idx == 0:
        return None

    prev = children[idx - 1]
    if prev.type == "comment":
        text = _ts_node_text(prev)
        if text.startswith("/**"):
            # Strip /** ... */ and clean up
            inner = text[3:]
            if inner.endswith("*/"):
                inner = inner[:-2]
            # Clean up leading * on each line
            cleaned_lines: list[str] = []
            for line in inner.split("\n"):
                stripped = line.strip()
                if stripped.startswith("* "):
                    cleaned_lines.append(stripped[2:])
                elif stripped.startswith("*"):
                    cleaned_lines.append(stripped[1:].lstrip())
                else:
                    cleaned_lines.append(stripped)
            return "\n".join(cleaned_lines).strip()
    return None


def _ts_get_name(node: Any) -> str | None:
    """Extract the name identifier from a declaration node."""
    name_node = node.child_by_field_name("name")
    if name_node:
        return _ts_node_text(name_node)
    # For method_definition, name is in property_identifier
    for child in node.children:
        if child.type in ("identifier", "property_identifier"):
            return _ts_node_text(child)
    return None


def _ts_get_params(node: Any) -> str:
    """Extract formal parameters text."""
    for child in node.children:
        if child.type == "formal_parameters":
            return _ts_node_text(child)
    return "()"


def _ts_get_body(node: Any) -> str | None:
    """Extract the statement_block body text."""
    for child in node.children:
        if child.type == "statement_block":
            return _ts_node_text(child)
    return None


def _ts_unwrap_export(node: Any) -> Any:
    """Unwrap export_statement to get the inner declaration."""
    if node.type == "export_statement":
        for child in node.children:
            if child.type in (
                "function_declaration",
                "class_declaration",
                "lexical_declaration",
            ):
                return child
    return node


def _ts_iter_declarations(root: Any) -> list[tuple[Any, Any]]:
    """Iterate top-level declarations, unwrapping exports.

    Returns (declaration_node, parent_for_jsdoc) pairs.
    """
    results: list[tuple[Any, Any]] = []
    for child in root.children:
        inner = _ts_unwrap_export(child)
        # For export_statement, JSDoc precedes the export_statement itself
        jsdoc_parent = root
        if inner.type in ("function_declaration", "class_declaration"):
            results.append((inner, jsdoc_parent))
        elif inner.type == "lexical_declaration":
            # const foo = (...) => {} — extract the arrow function
            for vc in inner.children:
                if vc.type == "variable_declarator":
                    results.append((vc, jsdoc_parent))
    return results


# ── Tree-sitter extraction functions ───────────────────────────────


def _ts_extract_functions(source: str, language: str) -> list[FunctionInfo]:
    """Extract functions from JS/TS using tree-sitter."""
    parser = _ts_get_parser(language)
    if parser is None:
        return _regex_extract_functions(source)

    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    functions: list[FunctionInfo] = []

    for decl, parent in _ts_iter_declarations(root):
        if decl.type == "function_declaration":
            fn = _ts_build_function_info(decl, parent, source)
            if fn:
                functions.append(fn)
        elif decl.type == "variable_declarator":
            fn = _ts_build_arrow_function_info(decl, parent, source)
            if fn:
                functions.append(fn)
        elif decl.type == "class_declaration":
            # Extract methods
            methods = _ts_extract_class_methods(decl, source)
            functions.extend(methods)

    return functions


def _ts_build_function_info(
    node: Any, parent: Any, source: str,
) -> FunctionInfo | None:
    """Build FunctionInfo from a function_declaration node."""
    name = _ts_get_name(node)
    if not name:
        return None

    start, end = _ts_node_lines(node)
    body = _ts_node_text(node)
    params = _ts_get_params(node)
    signature = f"function {name}{params}"

    # Check for async
    for child in node.children:
        if _ts_node_text(child) == "async":
            signature = f"async function {name}{params}"
            break

    jsdoc = _ts_find_jsdoc(
        # Find the right node for JSDoc: if parent has export wrapping, use the export
        parent.children[
            next(
                (i for i, c in enumerate(parent.children) if c.id == node.id),
                next(
                    (i for i, c in enumerate(parent.children)
                     if c.type == "export_statement" and any(
                         gc.id == node.id for gc in c.children
                     )),
                    0,
                ),
            )
        ] if parent.children else node,
        parent,
    )

    return FunctionInfo(
        name=name,
        body=body,
        signature=signature,
        line_start=start,
        line_end=end,
        docstring=jsdoc,
    )


def _ts_build_arrow_function_info(
    node: Any, parent: Any, source: str,
) -> FunctionInfo | None:
    """Build FunctionInfo from a variable_declarator with arrow_function."""
    name = _ts_get_name(node)
    if not name:
        return None

    # Find the arrow function child
    arrow_fn = None
    for child in node.children:
        if child.type == "arrow_function":
            arrow_fn = child
            break
    if arrow_fn is None:
        return None

    start, end = _ts_node_lines(node)
    body = _ts_node_text(node)
    params = _ts_get_params(arrow_fn)
    signature = f"const {name} = {params} =>"

    # JSDoc: find the lexical_declaration or export_statement parent
    jsdoc_target = None
    for p_child in parent.children:
        if p_child.type in ("lexical_declaration", "export_statement"):
            for gc in p_child.children:
                if gc.type == "lexical_declaration":
                    for ggc in gc.children:
                        if ggc.id == node.id:
                            jsdoc_target = p_child
                            break
                if gc.id == node.id:
                    jsdoc_target = p_child
                    break
        if jsdoc_target:
            break

    jsdoc = _ts_find_jsdoc(jsdoc_target or node, parent) if parent else None

    return FunctionInfo(
        name=name,
        body=body,
        signature=signature,
        line_start=start,
        line_end=end,
        docstring=jsdoc,
    )


def _ts_extract_class_methods(
    class_node: Any, source: str,
) -> list[FunctionInfo]:
    """Extract methods from a class declaration."""
    class_name = _ts_get_name(class_node)
    methods: list[FunctionInfo] = []

    # Find class_body
    class_body = None
    for child in class_node.children:
        if child.type == "class_body":
            class_body = child
            break
    if class_body is None:
        return methods

    for child in class_body.children:
        if child.type != "method_definition":
            continue

        name = _ts_get_name(child)
        if not name:
            continue

        start, end = _ts_node_lines(child)
        body = _ts_node_text(child)
        params = _ts_get_params(child)
        signature = f"{name}{params}"

        jsdoc = _ts_find_jsdoc(child, class_body)

        methods.append(FunctionInfo(
            name=name,
            body=body,
            signature=signature,
            line_start=start,
            line_end=end,
            docstring=jsdoc,
            is_method=True,
            class_name=class_name,
        ))

    return methods


def _ts_extract_classes(source: str, language: str) -> list[ClassInfo]:
    """Extract classes from JS/TS using tree-sitter."""
    parser = _ts_get_parser(language)
    if parser is None:
        return []

    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    classes: list[ClassInfo] = []

    for decl, parent in _ts_iter_declarations(root):
        if decl.type != "class_declaration":
            continue

        name = _ts_get_name(decl)
        if not name:
            continue

        start, end = _ts_node_lines(decl)
        body = _ts_node_text(decl)
        jsdoc = _ts_find_jsdoc(
            next(
                (c for c in parent.children
                 if c.type == "export_statement" and any(
                     gc.id == decl.id for gc in c.children
                 )),
                decl,
            ),
            parent,
        )

        methods_list = _ts_extract_class_methods(decl, source)

        # Build signature
        sig_parts = [f"class {name}"]
        if jsdoc:
            trunc = jsdoc[:200] + "..." if len(jsdoc) > 200 else jsdoc
            sig_parts.append(f"  /** {trunc} */")
        for m in methods_list:
            sig_parts.append(f"  {m.signature}")

        classes.append(ClassInfo(
            name=name,
            body=body,
            signature="\n".join(sig_parts),
            line_start=start,
            line_end=end,
            docstring=jsdoc,
            methods=tuple(methods_list),
        ))

    return classes


def _ts_extract_signatures(source: str, language: str) -> str | None:
    """Extract compact signatures from JS/TS using tree-sitter."""
    parser = _ts_get_parser(language)
    if parser is None:
        return _regex_extract_signatures(source)

    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    parts: list[str] = []

    for decl, parent in _ts_iter_declarations(root):
        if decl.type == "function_declaration":
            name = _ts_get_name(decl)
            params = _ts_get_params(decl)
            if name:
                jsdoc = _ts_find_jsdoc(
                    next(
                        (c for c in parent.children
                         if c.type == "export_statement" and any(
                             gc.id == decl.id for gc in c.children
                         )),
                        decl,
                    ),
                    parent,
                )
                sig = f"function {name}{params}"
                if jsdoc:
                    trunc = jsdoc[:200] + "..." if len(jsdoc) > 200 else jsdoc
                    parts.append(f"/** {trunc} */\n{sig}")
                else:
                    parts.append(sig)

        elif decl.type == "variable_declarator":
            name = _ts_get_name(decl)
            if name:
                for child in decl.children:
                    if child.type == "arrow_function":
                        params = _ts_get_params(child)
                        parts.append(f"const {name} = {params} =>")
                        break

        elif decl.type == "class_declaration":
            name = _ts_get_name(decl)
            if name:
                cls_parts = [f"class {name}"]
                methods = _ts_extract_class_methods(decl, source)
                for m in methods:
                    cls_parts.append(f"  {m.signature}")
                parts.append("\n".join(cls_parts))

    if not parts:
        lines = source.split("\n")
        return "\n".join(lines[:80])

    return "\n\n".join(parts)


def _ts_extract_docstring_pairs(
    source: str, language: str, min_chars: int,
) -> list[DocstringPair]:
    """Extract (JSDoc, code body) pairs from JS/TS."""
    parser = _ts_get_parser(language)
    if parser is None:
        return []

    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    pairs: list[DocstringPair] = []

    for decl, parent in _ts_iter_declarations(root):
        if decl.type == "function_declaration":
            name = _ts_get_name(decl)
            jsdoc_target = next(
                (c for c in parent.children
                 if c.type == "export_statement" and any(
                     gc.id == decl.id for gc in c.children
                 )),
                decl,
            )
            jsdoc = _ts_find_jsdoc(jsdoc_target, parent)
            body_node = _ts_get_body(decl)
            if name and jsdoc and body_node and len(jsdoc) >= min_chars:
                start, end = _ts_node_lines(decl)
                # Find the line where JSDoc ends (declaration start - 1)
                ds_end = start - 1
                pairs.append(DocstringPair(
                    name=name,
                    docstring=jsdoc,
                    code=body_node,
                    line_start=start,
                    docstring_end=ds_end if ds_end > 0 else start,
                    code_start=start,
                    code_end=end,
                ))

        elif decl.type == "class_declaration":
            # Extract method-level JSDoc pairs from class body
            class_body = None
            for child in decl.children:
                if child.type == "class_body":
                    class_body = child
                    break
            if class_body is None:
                continue

            for child in class_body.children:
                if child.type != "method_definition":
                    continue
                name = _ts_get_name(child)
                jsdoc = _ts_find_jsdoc(child, class_body)
                body_text = _ts_get_body(child)
                if name and jsdoc and body_text and len(jsdoc) >= min_chars:
                    start, end = _ts_node_lines(child)
                    pairs.append(DocstringPair(
                        name=name,
                        docstring=jsdoc,
                        code=body_text,
                        line_start=start,
                        docstring_end=start,
                        code_start=start,
                        code_end=end,
                    ))

    return pairs


def _ts_extract_imports(source: str, language: str) -> list[ImportInfo]:
    """Extract imports from JS/TS using tree-sitter."""
    parser = _ts_get_parser(language)
    if parser is None:
        return _regex_extract_imports(source)

    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    imports: list[ImportInfo] = []

    for child in root.children:
        if child.type != "import_statement":
            continue

        # Extract module path from the string node
        module = ""
        names: list[str] = []
        is_type_only = False
        line = child.start_point[0] + 1

        for c in child.children:
            if c.type == "string":
                # Remove quotes
                module = _ts_node_text(c).strip("\"'")
            elif c.type == "import_clause":
                for ic in c.children:
                    if ic.type == "named_imports":
                        for spec in ic.children:
                            if spec.type == "import_specifier":
                                name_node = spec.child_by_field_name("name")
                                if name_node:
                                    names.append(_ts_node_text(name_node))
                    elif ic.type == "identifier":
                        names.append(_ts_node_text(ic))
            elif c.type == "type" and _ts_node_text(c) == "type":
                is_type_only = True

        if module:
            imports.append(ImportInfo(
                module=module,
                names=tuple(names),
                line=line,
                is_type_only=is_type_only,
            ))

    return imports


# ── Regex fallback backend ─────────────────────────────────────────

_FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:pub\s+)?(?:fn|func|function|def)\s+(\w+)",
)
_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?class\s+(\w+)",
)
_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
)
_IMPORT_RE = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:\{[^}]*\}|[\w*]+)\s+from\s+['"]([^'"]+)['"]""",
)


def _regex_extract_functions(source: str) -> list[FunctionInfo]:
    """Regex fallback for function extraction when tree-sitter is unavailable."""
    lines = source.split("\n")
    functions: list[FunctionInfo] = []

    for i, line in enumerate(lines):
        match = _FUNC_RE.match(line)
        if not match:
            match = _ARROW_RE.match(line)
        if not match:
            continue

        name = match.group(1)
        # Take a reasonable body chunk (up to next function or 50 lines)
        body_end = min(i + 50, len(lines))
        for j in range(i + 1, body_end):
            if _FUNC_RE.match(lines[j]) or _CLASS_RE.match(lines[j]):
                body_end = j
                break

        body = "\n".join(lines[i:body_end])
        signature = line.rstrip()

        functions.append(FunctionInfo(
            name=name,
            body=body,
            signature=signature,
            line_start=i + 1,
            line_end=body_end,
        ))

    return functions


def _regex_extract_signatures(source: str) -> str | None:
    """Regex fallback for signature extraction."""
    lines = source.split("\n")
    sig_lines: list[str] = []

    for i, line in enumerate(lines):
        if _FUNC_RE.match(line) or _CLASS_RE.match(line) or _ARROW_RE.match(line):
            end = min(i + 3, len(lines))
            sig_lines.extend(lines[i:end])
            sig_lines.append("")

    if not sig_lines:
        return None
    return "\n".join(sig_lines[:60])


def _regex_extract_imports(source: str) -> list[ImportInfo]:
    """Regex fallback for import extraction."""
    imports: list[ImportInfo] = []
    for i, line in enumerate(source.split("\n")):
        match = _IMPORT_RE.match(line)
        if match:
            imports.append(ImportInfo(
                module=match.group(1),
                line=i + 1,
            ))
    return imports
