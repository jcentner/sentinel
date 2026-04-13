"""Tests for the language-agnostic source code extractor module."""

from __future__ import annotations

from sentinel.core.extractors import (
    ClassInfo,
    DocstringPair,
    FunctionInfo,
    ImportInfo,
    detect_language,
    extract_classes,
    extract_docstring_pairs,
    extract_functions,
    extract_imports,
    extract_signatures,
    has_tree_sitter,
    impl_name_from_test,
    is_test_file,
)

# ── Language detection ──────────────────────────────────────────────


def test_detect_language_python() -> None:
    assert detect_language("foo.py") == "python"


def test_detect_language_js() -> None:
    assert detect_language("app.js") == "javascript"
    assert detect_language("app.mjs") == "javascript"
    assert detect_language("app.cjs") == "javascript"
    assert detect_language("app.jsx") == "javascript"


def test_detect_language_ts() -> None:
    assert detect_language("app.ts") == "typescript"
    assert detect_language("app.tsx") == "typescript"
    assert detect_language("app.mts") == "typescript"


def test_detect_language_unsupported() -> None:
    assert detect_language("foo.go") is None
    assert detect_language("foo.rs") is None
    assert detect_language("README.md") is None


# ── Test file detection ─────────────────────────────────────────────


def test_is_test_file_python() -> None:
    assert is_test_file("test_config.py", "python")
    assert is_test_file("config_test.py", "python")
    assert not is_test_file("config.py", "python")


def test_is_test_file_js() -> None:
    assert is_test_file("config.test.js", "javascript")
    assert is_test_file("config.spec.js", "javascript")
    assert not is_test_file("config.js", "javascript")


def test_is_test_file_ts() -> None:
    assert is_test_file("config.test.ts", "typescript")
    assert is_test_file("config.spec.ts", "typescript")
    assert not is_test_file("config.ts", "typescript")


def test_is_test_file_by_directory() -> None:
    assert is_test_file("__tests__/config.js")
    assert is_test_file("tests/config.py")


# ── impl_name_from_test ─────────────────────────────────────────────


def test_impl_name_python() -> None:
    assert impl_name_from_test("test_config.py", "python") == "config.py"
    assert impl_name_from_test("config_test.py", "python") == "config.py"


def test_impl_name_js() -> None:
    assert impl_name_from_test("config.test.js", "javascript") == "config.js"
    assert impl_name_from_test("config.spec.js", "javascript") == "config.js"


def test_impl_name_ts() -> None:
    assert impl_name_from_test("config.test.ts", "typescript") == "config.ts"
    assert impl_name_from_test("config.spec.tsx", "typescript") == "config.tsx"


# ── Python extraction ───────────────────────────────────────────────

_PY_SOURCE = '''\
def greet(name: str) -> str:
    """Say hello to someone."""
    return f"Hello {name}"


class Calculator:
    """A simple calculator."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
'''


def test_py_extract_functions() -> None:
    funcs = extract_functions(_PY_SOURCE, "python")
    names = [f.name for f in funcs]
    assert "greet" in names
    assert "add" in names
    assert "subtract" in names

    greet = next(f for f in funcs if f.name == "greet")
    assert greet.docstring == "Say hello to someone."
    assert greet.line_start == 1
    assert not greet.is_method

    add = next(f for f in funcs if f.name == "add")
    assert add.is_method
    assert add.class_name == "Calculator"


def test_py_extract_classes() -> None:
    classes = extract_classes(_PY_SOURCE, "python")
    assert len(classes) == 1
    cls = classes[0]
    assert cls.name == "Calculator"
    assert cls.docstring == "A simple calculator."
    assert len(cls.methods) == 2
    assert "add" in cls.signature
    assert "subtract" in cls.signature


def test_py_extract_signatures() -> None:
    sigs = extract_signatures(_PY_SOURCE, "python")
    assert sigs is not None
    assert "def greet" in sigs
    assert "class Calculator" in sigs
    assert "def add" in sigs


def test_py_extract_docstring_pairs() -> None:
    pairs = extract_docstring_pairs(_PY_SOURCE, "python", min_docstring_chars=10)
    names = [p.name for p in pairs]
    assert "greet" in names
    assert "Calculator" in names
    assert "add" in names

    greet = next(p for p in pairs if p.name == "greet")
    assert greet.docstring == "Say hello to someone."
    assert "return" in greet.code


def test_py_extract_docstring_pairs_min_chars() -> None:
    pairs = extract_docstring_pairs(_PY_SOURCE, "python", min_docstring_chars=100)
    assert len(pairs) == 0  # All docstrings are shorter than 100


def test_py_extract_imports() -> None:
    source = """\
import os
from pathlib import Path
from sentinel.config import SentinelConfig
"""
    imports = extract_imports(source, "python")
    assert len(imports) == 3
    assert imports[0].module == "os"
    assert imports[1].module == "pathlib"
    assert imports[1].names == ("Path",)
    assert imports[2].module == "sentinel.config"
    assert imports[2].names == ("SentinelConfig",)


def test_py_syntax_error_returns_empty() -> None:
    assert extract_functions("def broken(:", "python") == []
    assert extract_classes("class Bad(:", "python") == []
    assert extract_docstring_pairs("def bad(:", "python") == []


def test_py_signatures_syntax_error_returns_first_lines() -> None:
    source = "this is not python\nbut has some content"
    result = extract_signatures(source, "python")
    assert result is not None
    assert "this is not python" in result


# ── JS/TS extraction (tree-sitter) ──────────────────────────────────

_JS_SOURCE = '''\
/**
 * Calculates the sum of two numbers.
 * @param {number} a - First number
 * @param {number} b - Second number
 * @returns {number} The sum
 */
function add(a, b) {
    return a + b;
}

class Calculator {
    /** Creates a calculator instance */
    constructor() {
        this.history = [];
    }

    /** Multiplies two numbers */
    multiply(a, b) {
        const result = a * b;
        this.history.push(result);
        return result;
    }
}

const greet = (name) => {
    return `Hello ${name}!`;
};
'''

_TS_SOURCE = '''\
/**
 * Adds two numbers together.
 * @param a - First number
 * @param b - Second number
 */
export function add(a: number, b: number): number {
    return a + b;
}

export class Calculator {
    private history: number[] = [];

    /** Multiplies two numbers */
    multiply(a: number, b: number): number {
        const result = a * b;
        this.history.push(result);
        return result;
    }
}

import { something } from "./other-module";
import type { Config } from "../types";
'''


def test_js_extract_functions() -> None:
    if not has_tree_sitter():
        return  # Skip if tree-sitter not installed
    funcs = extract_functions(_JS_SOURCE, "javascript")
    names = [f.name for f in funcs]
    assert "add" in names
    assert "constructor" in names
    assert "multiply" in names
    # greet is an arrow function
    assert "greet" in names

    add = next(f for f in funcs if f.name == "add")
    assert add.docstring is not None
    assert "sum" in add.docstring.lower()
    assert not add.is_method

    multiply = next(f for f in funcs if f.name == "multiply")
    assert multiply.is_method
    assert multiply.class_name == "Calculator"
    assert multiply.docstring is not None


def test_js_extract_classes() -> None:
    if not has_tree_sitter():
        return
    classes = extract_classes(_JS_SOURCE, "javascript")
    assert len(classes) == 1
    cls = classes[0]
    assert cls.name == "Calculator"
    assert len(cls.methods) == 2
    method_names = [m.name for m in cls.methods]
    assert "constructor" in method_names
    assert "multiply" in method_names


def test_js_extract_signatures() -> None:
    if not has_tree_sitter():
        return
    sigs = extract_signatures(_JS_SOURCE, "javascript")
    assert sigs is not None
    assert "function add" in sigs
    assert "class Calculator" in sigs


def test_js_extract_docstring_pairs() -> None:
    if not has_tree_sitter():
        return
    pairs = extract_docstring_pairs(_JS_SOURCE, "javascript", min_docstring_chars=10)
    names = [p.name for p in pairs]
    assert "add" in names
    # Method-level JSDoc
    assert "multiply" in names


def test_ts_extract_functions() -> None:
    if not has_tree_sitter():
        return
    funcs = extract_functions(_TS_SOURCE, "typescript")
    names = [f.name for f in funcs]
    assert "add" in names
    assert "multiply" in names


def test_ts_extract_imports() -> None:
    if not has_tree_sitter():
        return
    imports = extract_imports(_TS_SOURCE, "typescript")
    modules = [i.module for i in imports]
    assert "./other-module" in modules
    assert "../types" in modules

    type_import = next(i for i in imports if i.module == "../types")
    assert type_import.is_type_only

    regular = next(i for i in imports if i.module == "./other-module")
    assert not regular.is_type_only
    assert "something" in regular.names


def test_ts_extract_classes_with_export() -> None:
    if not has_tree_sitter():
        return
    classes = extract_classes(_TS_SOURCE, "typescript")
    assert len(classes) == 1
    assert classes[0].name == "Calculator"


# ── Unsupported language returns empty ───────────────────────────────


def test_unsupported_language() -> None:
    assert extract_functions("fn main() {}", "rust") == []
    assert extract_classes("struct Foo {}", "rust") == []
    assert extract_docstring_pairs("fn main() {}", "rust") == []
    assert extract_imports("use std::io;", "rust") == []
    assert extract_signatures("fn main() {}", "rust") is None


# ── Regex fallback ───────────────────────────────────────────────────


def test_regex_fallback_functions() -> None:
    """Test regex fallback extracts basic function signatures."""
    from sentinel.core.extractors import _regex_extract_functions

    source = """\
function add(a, b) {
    return a + b;
}

function subtract(a, b) {
    return a - b;
}
"""
    funcs = _regex_extract_functions(source)
    names = [f.name for f in funcs]
    assert "add" in names
    assert "subtract" in names


def test_regex_fallback_signatures() -> None:
    from sentinel.core.extractors import _regex_extract_signatures

    source = """\
function add(a, b) {
    return a + b;
}

class Calculator {
    multiply(a, b) {}
}
"""
    sigs = _regex_extract_signatures(source)
    assert sigs is not None
    assert "function add" in sigs
    assert "class Calculator" in sigs
