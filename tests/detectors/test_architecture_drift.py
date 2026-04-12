"""Tests for the architecture drift detector."""

from __future__ import annotations

import pytest

from sentinel.detectors.architecture_drift import (
    ArchitectureDrift,
    _collect_import_edges,
    _find_layer,
    _in_shared,
    _module_matches,
    _parse_forbidden,
    _path_to_module,
    _resolve_import,
)
from sentinel.models import DetectorContext, DetectorTier


@pytest.fixture
def detector():
    return ArchitectureDrift()


@pytest.fixture
def make_context(tmp_path):
    """Factory for DetectorContext pointing at a tmp repo."""

    def _make(**kwargs):
        defaults = {
            "repo_root": str(tmp_path),
            "config": {},
            "target_paths": None,
            "changed_files": None,
        }
        defaults.update(kwargs)
        return DetectorContext(**defaults)

    return _make


# ── Metadata ────────────────────────────────────────────────────────


class TestMetadata:
    def test_name(self, detector):
        assert detector.name == "architecture-drift"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, detector):
        assert "config-drift" in detector.categories

    def test_registered(self):
        from sentinel.detectors.base import get_registry

        registry = get_registry()
        assert "architecture-drift" in registry


# ── Helper functions ────────────────────────────────────────────────


class TestPathToModule:
    def test_basic(self, tmp_path):
        path = tmp_path / "myapp" / "core" / "runner.py"
        result = _path_to_module(path, tmp_path)
        assert result == "myapp.core.runner"

    def test_src_prefix(self, tmp_path):
        path = tmp_path / "src" / "myapp" / "core.py"
        result = _path_to_module(path, tmp_path)
        assert result == "myapp.core"

    def test_init_file(self, tmp_path):
        path = tmp_path / "myapp" / "__init__.py"
        result = _path_to_module(path, tmp_path)
        assert result == "myapp"

    def test_top_level(self, tmp_path):
        path = tmp_path / "setup.py"
        result = _path_to_module(path, tmp_path)
        assert result == "setup"


class TestModuleMatches:
    def test_exact_match(self):
        assert _module_matches("myapp.core", "myapp.core")

    def test_prefix_match(self):
        assert _module_matches("myapp.core.runner", "myapp.core")

    def test_no_match(self):
        assert not _module_matches("myapp.web", "myapp.core")

    def test_partial_name_no_match(self):
        """myapp.cores shouldn't match myapp.core."""
        assert not _module_matches("myapp.cores", "myapp.core")


class TestInShared:
    def test_in_shared(self):
        shared = frozenset({"myapp.models", "myapp.config"})
        assert _in_shared("myapp.models", shared)
        assert _in_shared("myapp.models.base", shared)
        assert _in_shared("myapp.config", shared)

    def test_not_in_shared(self):
        shared = frozenset({"myapp.models"})
        assert not _in_shared("myapp.core", shared)


class TestFindLayer:
    def test_finds_layer(self):
        ranks = {"myapp.web": 0, "myapp.core": 1, "myapp.store": 2}
        assert _find_layer("myapp.core.runner", ranks) == "myapp.core"

    def test_finds_most_specific(self):
        ranks = {"myapp": 0, "myapp.core": 1, "myapp.core.inner": 2}
        assert _find_layer("myapp.core.inner.mod", ranks) == "myapp.core.inner"

    def test_not_in_any_layer(self):
        ranks = {"myapp.web": 0}
        assert _find_layer("other.module", ranks) is None


class TestParseForbidden:
    def test_basic(self):
        rules = ["myapp.store -> myapp.web", "myapp.detectors -> myapp.cli"]
        result = _parse_forbidden(rules)
        assert result == [
            ("myapp.store", "myapp.web"),
            ("myapp.detectors", "myapp.cli"),
        ]

    def test_ignores_malformed(self):
        rules = ["not a rule", "a.b -> c.d"]
        result = _parse_forbidden(rules)
        assert len(result) == 1


# ── Import edge collection ──────────────────────────────────────────


class TestCollectEdges:
    def test_collects_import(self, tmp_path):
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("import myapp.store\n")
        edges = _collect_import_edges(tmp_path)
        targets = [e[1] for e in edges if e[0] == "myapp.core"]
        assert "myapp.store" in targets

    def test_collects_from_import(self, tmp_path):
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "web.py").write_text("from myapp.core import runner\n")
        edges = _collect_import_edges(tmp_path)
        targets = [e[1] for e in edges if e[0] == "myapp.web"]
        assert "myapp.core" in targets

    def test_skips_common_dirs(self, tmp_path):
        venv = tmp_path / ".venv" / "lib" / "mod.py"
        venv.parent.mkdir(parents=True)
        venv.write_text("import os\n")
        edges = _collect_import_edges(tmp_path)
        sources = [e[0] for e in edges]
        assert not any(".venv" in s for s in sources)

    def test_handles_syntax_error(self, tmp_path):
        (tmp_path / "bad.py").write_text("def f(\n")
        edges = _collect_import_edges(tmp_path)
        assert edges == []

    def test_collects_relative_import(self, tmp_path):
        """Relative imports are resolved to full module paths."""
        pkg = tmp_path / "myapp" / "store"
        pkg.mkdir(parents=True)
        (tmp_path / "myapp" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("")
        (pkg / "db.py").write_text("from .helpers import utils\n")
        edges = _collect_import_edges(tmp_path)
        targets = [e[1] for e in edges if e[0] == "myapp.store.db"]
        assert "myapp.store.helpers" in targets

    def test_collects_parent_relative_import(self, tmp_path):
        """Level-2 relative imports are resolved correctly."""
        pkg = tmp_path / "myapp" / "store"
        pkg.mkdir(parents=True)
        (tmp_path / "myapp" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("")
        (pkg / "db.py").write_text("from ..core import runner\n")
        edges = _collect_import_edges(tmp_path)
        targets = [e[1] for e in edges if e[0] == "myapp.store.db"]
        assert "myapp.core" in targets


# ── Resolve import ──────────────────────────────────────────────────


class TestResolveImport:
    def test_absolute_import(self):
        assert _resolve_import("myapp.core", "os.path", 0) == "os.path"

    def test_level_1_relative(self):
        result = _resolve_import("myapp.store.db", "helpers", 1)
        assert result == "myapp.store.helpers"

    def test_level_2_relative(self):
        result = _resolve_import("myapp.store.db", "core", 2)
        assert result == "myapp.core"

    def test_bare_relative_import(self):
        """from . import foo — module is None at level 1."""
        result = _resolve_import("myapp.store.db", None, 1)
        assert result == "myapp.store"

    def test_too_many_levels(self):
        result = _resolve_import("myapp", "foo", 5)
        assert result is None

    def test_absolute_none_module(self):
        assert _resolve_import("myapp", None, 0) is None


# ── Layer violation detection ───────────────────────────────────────


class TestLayerViolation:
    def test_lower_imports_higher(self, detector, tmp_path):
        """Store importing from web is a layer violation."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        store = pkg / "store"
        store.mkdir()
        (store / "__init__.py").write_text("")
        (store / "db.py").write_text("from myapp.web import routes\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": ["myapp.web", "myapp.core", "myapp.store"],
                    "shared": [],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "layer violation" in findings[0].title
        assert findings[0].severity.value == "medium"
        assert findings[0].confidence == 0.90

    def test_higher_imports_lower_ok(self, detector, tmp_path):
        """Web importing from store is fine (higher importing lower)."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "web.py").write_text("from myapp.store import db\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": ["myapp.web", "myapp.core", "myapp.store"],
                    "shared": [],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_same_layer_ok(self, detector, tmp_path):
        """Imports within the same layer are fine."""
        pkg = tmp_path / "myapp" / "core"
        pkg.mkdir(parents=True)
        (tmp_path / "myapp" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("")
        (pkg / "runner.py").write_text("from myapp.core import utils\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": ["myapp.web", "myapp.core", "myapp.store"],
                    "shared": [],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_shared_module_exempt(self, detector, tmp_path):
        """Shared modules can be imported from any layer."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        store = pkg / "store"
        store.mkdir()
        (store / "__init__.py").write_text("")
        (store / "db.py").write_text("from myapp.models import Finding\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": [
                        "myapp.web",
                        "myapp.models",
                        "myapp.store",
                    ],
                    "shared": ["myapp.models"],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_module_not_in_any_layer(self, detector, tmp_path):
        """Modules not in any declared layer are ignored."""
        pkg = tmp_path / "tests"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "test_core.py").write_text("from myapp.web import app\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": ["myapp.web", "myapp.core"],
                    "shared": [],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 0


# ── Forbidden imports ───────────────────────────────────────────────


class TestForbiddenImports:
    def test_forbidden_import_detected(self, detector, tmp_path):
        """Explicitly forbidden imports produce findings."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "store.py").write_text("from myapp.web import handler\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": [],
                    "forbidden": ["myapp.store -> myapp.web"],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "forbidden import" in findings[0].title
        assert findings[0].severity.value == "high"
        assert findings[0].confidence == 0.95

    def test_non_forbidden_import_ok(self, detector, tmp_path):
        """Non-forbidden imports pass."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("from myapp.store import db\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": [],
                    "forbidden": ["myapp.store -> myapp.web"],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 0


# ── Config reading ──────────────────────────────────────────────────


class TestConfigReading:
    def test_no_config_skips(self, detector, make_context):
        """No architecture config means no findings."""
        ctx = make_context()
        findings = detector.detect(ctx)
        assert findings == []

    def test_reads_from_sentinel_toml(self, detector, tmp_path):
        """Reads [sentinel.architecture] from sentinel.toml."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        store = pkg / "store"
        store.mkdir()
        (store / "__init__.py").write_text("")
        (store / "db.py").write_text("from myapp.web import routes\n")

        (tmp_path / "sentinel.toml").write_text(
            "[sentinel.architecture]\n"
            'layers = ["myapp.web", "myapp.core", "myapp.store"]\n'
            "shared = []\n"
        )

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={},
        )
        findings = detector.detect(ctx)
        assert len(findings) == 1

    def test_empty_layers_and_forbidden(self, detector, make_context):
        """Empty layers and no forbidden = no findings."""
        ctx = make_context(config={"architecture": {"layers": []}})
        findings = detector.detect(ctx)
        assert findings == []


# ── Finding structure ───────────────────────────────────────────────


class TestFindingStructure:
    def test_finding_metadata(self, detector, tmp_path):
        """Verify finding has correct fields."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        store = pkg / "store"
        store.mkdir()
        (store / "__init__.py").write_text("")
        (store / "db.py").write_text("from myapp.web import app\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "architecture": {
                    "layers": ["myapp.web", "myapp.store"],
                    "shared": [],
                },
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 1
        f = findings[0]
        assert f.detector == "architecture-drift"
        assert f.category == "config-drift"
        assert f.file_path == "myapp/store/db.py"
        assert f.evidence[0].type.value == "code"
        assert f.context["violation_type"] == "layer violation"
        assert f.context["source_module"] == "myapp.store.db"
        assert f.context["target_module"] == "myapp.web"

    def test_exception_returns_empty(self, detector, make_context, monkeypatch):
        """Exceptions in detect() are caught and return empty list."""
        monkeypatch.setattr(
            detector,
            "_run",
            lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert findings == []
