"""Tests for the dead-code / unused exports detector."""

from __future__ import annotations

import textwrap
from pathlib import Path

from sentinel.detectors.base import get_registry
from sentinel.detectors.dead_code import (
    DeadCodeDetector,
    _find_unused_js_symbols,
    _find_unused_python_symbols,
    _ModuleInfo,
    _parse_js_module,
    _parse_python_module,
    _python_module_path,
    _Symbol,
)
from sentinel.models import DetectorContext, DetectorTier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, content: str) -> Path:
    """Write a file under *root* and return its path."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


def _ctx(root: Path) -> DetectorContext:
    return DetectorContext(repo_root=str(root))


# ---------------------------------------------------------------------------
# Python module parsing
# ---------------------------------------------------------------------------

class TestParsePythonModule:
    def test_functions_and_classes(self, tmp_path: Path) -> None:
        _write(tmp_path, "mod.py", """\
            def foo():
                pass
            class Bar:
                pass
        """)
        info = _parse_python_module(tmp_path / "mod.py", "mod.py")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "foo" in names
        assert "Bar" in names

    def test_constants(self, tmp_path: Path) -> None:
        _write(tmp_path, "settings.py", """\
            MAX_RETRIES = 3
            API_URL = "https://example.com"
            local_var = 42
        """)
        info = _parse_python_module(tmp_path / "settings.py", "settings.py")
        assert info is not None
        names = {s.name for s in info.defined}
        # Only UPPER_CASE are treated as constants
        assert "MAX_RETRIES" in names
        assert "API_URL" in names
        assert "local_var" not in names

    def test_imports_tracked(self, tmp_path: Path) -> None:
        _write(tmp_path, "mod.py", """\
            import os
            import sentinel.models
            from pathlib import Path
            from sentinel.models import Finding
        """)
        info = _parse_python_module(tmp_path / "mod.py", "mod.py")
        assert info is not None
        assert "os" in info.imported_names
        assert "Path" in info.imported_names
        assert "Finding" in info.imported_names
        # Only `import X` adds to imported_modules, not `from X import y`
        assert "sentinel.models" in info.imported_modules
        assert "os" in info.imported_modules
        assert "pathlib" not in info.imported_modules

    def test_all_limits_exports(self, tmp_path: Path) -> None:
        _write(tmp_path, "mod.py", """\
            __all__ = ["foo"]
            def foo():
                pass
            def bar():
                pass
        """)
        info = _parse_python_module(tmp_path / "mod.py", "mod.py")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "foo" in names
        assert "bar" not in names

    def test_syntax_error_returns_none(self, tmp_path: Path) -> None:
        _write(tmp_path, "bad.py", "def foo(:\n")
        assert _parse_python_module(tmp_path / "bad.py", "bad.py") is None

    def test_internal_refs_collected(self, tmp_path: Path) -> None:
        """Parser should collect intra-file references in internal_refs."""
        _write(tmp_path, "mod.py", """\
            MY_CONST = 42

            def use_const():
                return MY_CONST + 1
        """)
        info = _parse_python_module(tmp_path / "mod.py", "mod.py")
        assert info is not None
        assert "MY_CONST" in info.internal_refs

    def test_async_functions(self, tmp_path: Path) -> None:
        _write(tmp_path, "async_mod.py", """\
            async def handle_request():
                pass
        """)
        info = _parse_python_module(tmp_path / "async_mod.py", "async_mod.py")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "handle_request" in names


# ---------------------------------------------------------------------------
# JS/TS module parsing
# ---------------------------------------------------------------------------

class TestParseJsModule:
    def test_export_function(self, tmp_path: Path) -> None:
        _write(tmp_path, "utils.ts", """\
            export function calculateTotal(items) {
                return items.reduce((s, i) => s + i.price, 0);
            }
        """)
        info = _parse_js_module(tmp_path / "utils.ts", "utils.ts")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "calculateTotal" in names

    def test_export_class(self, tmp_path: Path) -> None:
        _write(tmp_path, "service.ts", """\
            export class UserService {
                getUser() {}
            }
        """)
        info = _parse_js_module(tmp_path / "service.ts", "service.ts")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "UserService" in names

    def test_export_const(self, tmp_path: Path) -> None:
        _write(tmp_path, "config.ts", """\
            export const API_URL = "https://api.example.com";
            export const maxRetries = 3;
        """)
        info = _parse_js_module(tmp_path / "config.ts", "config.ts")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "API_URL" in names
        assert "maxRetries" in names

    def test_named_export(self, tmp_path: Path) -> None:
        _write(tmp_path, "mod.ts", """\
            function internal() {}
            function publicFn() {}
            export { publicFn }
        """)
        info = _parse_js_module(tmp_path / "mod.ts", "mod.ts")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "publicFn" in names
        # 'internal' is not exported, should not be in defined
        # (but our regex-based approach only captures export statements)
        assert "internal" not in names

    def test_named_export_with_alias(self, tmp_path: Path) -> None:
        _write(tmp_path, "mod.ts", """\
            function internalFn() {}
            export { internalFn as publicFn }
        """)
        info = _parse_js_module(tmp_path / "mod.ts", "mod.ts")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "publicFn" in names

    def test_imports_tracked(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.ts", """\
            import { useState } from 'react';
            import axios from 'axios';
        """)
        info = _parse_js_module(tmp_path / "app.ts", "app.ts")
        assert info is not None
        assert "useState" in info.imported_names
        assert "axios" in info.imported_names

    def test_export_default_function(self, tmp_path: Path) -> None:
        _write(tmp_path, "page.tsx", """\
            export default function HomePage() {
                return <div>Home</div>;
            }
        """)
        info = _parse_js_module(tmp_path / "page.tsx", "page.tsx")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "HomePage" in names

    def test_export_async_function(self, tmp_path: Path) -> None:
        _write(tmp_path, "api.ts", """\
            export async function fetchData() {
                return await fetch('/api');
            }
        """)
        info = _parse_js_module(tmp_path / "api.ts", "api.ts")
        assert info is not None
        names = {s.name for s in info.defined}
        assert "fetchData" in names

    def test_auto_generated_file_skipped(self, tmp_path: Path) -> None:
        """Auto-generated JS files should be skipped entirely."""
        _write(tmp_path, "index.ts", """\
            // Auto-generated by scripts/build-registry.ts
            export function GeneratedWidget() { return 1; }
        """)
        info = _parse_js_module(tmp_path / "index.ts", "index.ts")
        assert info is None

    def test_dynamic_import_tracked(self, tmp_path: Path) -> None:
        """Dynamic import() calls should count as module usage."""
        _write(tmp_path, "loader.ts", """\
            const mod = import('./widgets/button');
            const lazy = import("./widgets/card");
        """)
        info = _parse_js_module(tmp_path / "loader.ts", "loader.ts")
        assert info is not None
        assert "./widgets/button" in info.imported_modules
        assert "./widgets/card" in info.imported_modules


# ---------------------------------------------------------------------------
# Python module path conversion
# ---------------------------------------------------------------------------

class TestPythonModulePath:
    def test_simple(self) -> None:
        assert _python_module_path("sentinel/models.py") == "sentinel.models"

    def test_with_src_prefix(self) -> None:
        assert _python_module_path("src/sentinel/models.py") == "sentinel.models"

    def test_nested(self) -> None:
        assert (
            _python_module_path("src/sentinel/detectors/base.py")
            == "sentinel.detectors.base"
        )


# ---------------------------------------------------------------------------
# Cross-referencing
# ---------------------------------------------------------------------------

class TestCrossReferencing:
    def test_unused_symbol_detected(self) -> None:
        modules = [
            _ModuleInfo(
                path="utils.py",
                defined=[_Symbol("helper", "utils.py", 1, "function")],
                imported_names=set(),
                imported_modules=set(),
            ),
            _ModuleInfo(
                path="main.py",
                defined=[],
                imported_names={"os"},
                imported_modules={"os"},
            ),
        ]
        unused = _find_unused_python_symbols(modules)
        assert len(unused) == 1
        assert unused[0].name == "helper"

    def test_used_symbol_not_flagged(self) -> None:
        modules = [
            _ModuleInfo(
                path="utils.py",
                defined=[_Symbol("helper", "utils.py", 1, "function")],
                imported_names=set(),
                imported_modules=set(),
            ),
            _ModuleInfo(
                path="main.py",
                defined=[],
                imported_names={"helper"},
                imported_modules={"utils"},
            ),
        ]
        unused = _find_unused_python_symbols(modules)
        assert len(unused) == 0

    def test_module_import_counts_as_used(self) -> None:
        """If someone does `import mymod`, all symbols in mymod are considered used."""
        modules = [
            _ModuleInfo(
                path="src/sentinel/models.py",
                defined=[_Symbol("Finding", "src/sentinel/models.py", 10, "class")],
                imported_names=set(),
                imported_modules=set(),
            ),
            _ModuleInfo(
                path="src/sentinel/runner.py",
                defined=[],
                imported_names=set(),
                imported_modules={"sentinel.models"},
            ),
        ]
        unused = _find_unused_python_symbols(modules)
        assert len(unused) == 0

    def test_private_symbols_skipped(self) -> None:
        modules = [
            _ModuleInfo(
                path="utils.py",
                defined=[_Symbol("_internal", "utils.py", 1, "function")],
                imported_names=set(),
                imported_modules=set(),
            ),
        ]
        unused = _find_unused_python_symbols(modules)
        assert len(unused) == 0

    def test_dunder_methods_skipped(self) -> None:
        modules = [
            _ModuleInfo(
                path="model.py",
                defined=[_Symbol("__init__", "model.py", 1, "function")],
                imported_names=set(),
                imported_modules=set(),
            ),
        ]
        unused = _find_unused_python_symbols(modules)
        assert len(unused) == 0

    def test_js_unused_export(self) -> None:
        modules = [
            _ModuleInfo(
                path="utils.ts",
                defined=[_Symbol("deadHelper", "utils.ts", 5, "function")],
                imported_names=set(),
                imported_modules=set(),
            ),
            _ModuleInfo(
                path="app.ts",
                defined=[],
                imported_names={"liveHelper"},
                imported_modules={"./utils"},
            ),
        ]
        unused = _find_unused_js_symbols(modules)
        assert len(unused) == 1
        assert unused[0].name == "deadHelper"

    def test_js_used_export_not_flagged(self) -> None:
        modules = [
            _ModuleInfo(
                path="utils.ts",
                defined=[_Symbol("helper", "utils.ts", 5, "function")],
                imported_names=set(),
                imported_modules=set(),
            ),
            _ModuleInfo(
                path="app.ts",
                defined=[],
                imported_names={"helper"},
                imported_modules={"./utils"},
            ),
        ]
        unused = _find_unused_js_symbols(modules)
        assert len(unused) == 0

    def test_js_always_used_skipped(self) -> None:
        modules = [
            _ModuleInfo(
                path="page.tsx",
                defined=[_Symbol("App", "page.tsx", 1, "function")],
                imported_names=set(),
                imported_modules=set(),
            ),
        ]
        unused = _find_unused_js_symbols(modules)
        assert len(unused) == 0

    def test_intra_file_usage_not_flagged(self) -> None:
        """A symbol referenced within its own module should not be flagged."""
        modules = [
            _ModuleInfo(
                path="utils.py",
                defined=[_Symbol("CI_VARS", "utils.py", 1, "constant")],
                imported_names=set(),
                imported_modules=set(),
                internal_refs={"CI_VARS"},
            ),
        ]
        unused = _find_unused_python_symbols(modules)
        assert len(unused) == 0


# ---------------------------------------------------------------------------
# Full detector integration
# ---------------------------------------------------------------------------

class TestDeadCodeDetector:
    def test_empty_repo(self, tmp_path: Path) -> None:
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert findings == []

    def test_all_used_no_findings(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/utils.py", """\
            def helper():
                return 42
        """)
        _write(tmp_path, "src/main.py", """\
            from utils import helper
            print(helper())
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert len(findings) == 0

    def test_unused_function_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/utils.py", """\
            def used_fn():
                return 1
            def unused_fn():
                return 2
        """)
        _write(tmp_path, "src/main.py", """\
            from utils import used_fn
            print(used_fn())
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        names = {f.title for f in findings}
        assert "Unused function: unused_fn" in names
        assert "Unused function: used_fn" not in names

    def test_unused_class_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "models.py", """\
            class UsedModel:
                pass
            class DeadModel:
                pass
        """)
        _write(tmp_path, "app.py", """\
            from models import UsedModel
            m = UsedModel()
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        names = {f.title for f in findings}
        assert "Unused class: DeadModel" in names
        assert "Unused class: UsedModel" not in names

    def test_test_files_dont_generate_findings(self, tmp_path: Path) -> None:
        """Symbols defined in test files should not be flagged."""
        _write(tmp_path, "test_utils.py", """\
            def test_helper():
                pass
            def another_test():
                pass
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert len(findings) == 0

    def test_test_imports_count_as_usage(self, tmp_path: Path) -> None:
        """If a test imports a symbol, that symbol is considered used."""
        _write(tmp_path, "utils.py", """\
            def helper():
                return 42
        """)
        _write(tmp_path, "test_utils.py", """\
            from utils import helper
            def test_it():
                assert helper() == 42
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert len(findings) == 0

    def test_init_files_skipped(self, tmp_path: Path) -> None:
        """__init__.py re-exports should not be flagged."""
        _write(tmp_path, "pkg/__init__.py", """\
            from .core import Engine
        """)
        _write(tmp_path, "pkg/core.py", """\
            class Engine:
                pass
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        # Engine is imported by __init__.py — not unused
        assert len(findings) == 0

    def test_conftest_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "conftest.py", """\
            import pytest
            @pytest.fixture
            def my_fixture():
                return 42
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert len(findings) == 0

    def test_intra_file_constant_usage(self, tmp_path: Path) -> None:
        """Constants used within the same file should not be flagged (TD-040)."""
        _write(tmp_path, "utils.py", """\
            CI_VARIABLES = ("CI", "GITHUB_ACTIONS", "TRAVIS")

            def looks_like_ci():
                import os
                return any(os.environ.get(v) for v in CI_VARIABLES)
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        names = {f.title for f in findings}
        assert "Unused constant: CI_VARIABLES" not in names

    def test_intra_file_function_call(self, tmp_path: Path) -> None:
        """Functions called within the same file should not be flagged (TD-040)."""
        _write(tmp_path, "helpers.py", """\
            def compute_total(items):
                return sum(items)

            def report():
                total = compute_total([1, 2, 3])
                print(total)
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        names = {f.title for f in findings}
        assert "Unused function: compute_total" not in names

    def test_pep517_build_hooks_not_flagged(self, tmp_path: Path) -> None:
        """PEP 517 build backend hooks should not be flagged (TD-040)."""
        _write(tmp_path, "backend.py", """\
            def get_requires_for_build_sdist(config_settings=None):
                return []
            def get_requires_for_build_wheel(config_settings=None):
                return []
            def get_requires_for_build_editable(config_settings=None):
                return []
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert len(findings) == 0

    def test_skips_common_dirs(self, tmp_path: Path) -> None:
        """Files in node_modules, .venv, etc. should be skipped."""
        _write(tmp_path, "node_modules/pkg/index.js", """\
            export function internal() {}
        """)
        _write(tmp_path, ".venv/lib/site.py", """\
            def configure():
                pass
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert len(findings) == 0

    def test_js_unused_export(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/helpers.ts", """\
            export function usedHelper() { return 1; }
            export function deadHelper() { return 2; }
        """)
        _write(tmp_path, "src/app.ts", """\
            import { usedHelper } from './helpers';
            console.log(usedHelper());
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        names = {f.title for f in findings}
        assert "Unused export: deadHelper" in names
        assert "Unused export: usedHelper" not in names

    def test_finding_metadata(self, tmp_path: Path) -> None:
        _write(tmp_path, "lib.py", """\
            def orphan():
                pass
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        assert len(findings) == 1
        f = findings[0]
        assert f.detector == "dead-code"
        assert f.category == "code-quality"
        assert f.severity.value == "low"
        assert f.confidence == 0.7
        assert f.file_path == "lib.py"
        assert f.line_start == 1
        assert len(f.evidence) == 1

    def test_mixed_python_and_js(self, tmp_path: Path) -> None:
        _write(tmp_path, "utils.py", """\
            def py_dead():
                pass
        """)
        _write(tmp_path, "helpers.ts", """\
            export function jsDead() { return 1; }
        """)
        det = DeadCodeDetector()
        findings = det.detect(_ctx(tmp_path))
        names = {f.title for f in findings}
        assert "Unused function: py_dead" in names
        assert "Unused export: jsDead" in names


# ---------------------------------------------------------------------------
# Detector meta
# ---------------------------------------------------------------------------

class TestDetectorMeta:
    def test_name(self) -> None:
        assert DeadCodeDetector().name == "dead-code"

    def test_tier(self) -> None:
        assert DeadCodeDetector().tier == DetectorTier.HEURISTIC

    def test_categories(self) -> None:
        assert DeadCodeDetector().categories == ["code-quality"]

    def test_registered(self) -> None:
        assert "dead-code" in get_registry()
