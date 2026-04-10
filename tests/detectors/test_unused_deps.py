"""Tests for the unused dependencies detector."""

from __future__ import annotations

import pytest

from sentinel.detectors.unused_deps import (
    UnusedDeps,
    _expected_import_names,
    _normalize_package_name,
    _strip_version,
)
from sentinel.models import DetectorContext, DetectorTier


@pytest.fixture
def detector():
    return UnusedDeps()


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


# ── Unit tests for helpers ──────────────────────────────────────────


class TestNormalizePackageName:
    def test_lowercase(self):
        assert _normalize_package_name("Requests") == "requests"

    def test_hyphens(self):
        assert _normalize_package_name("python-dateutil") == "python_dateutil"

    def test_dots(self):
        assert _normalize_package_name("ruamel.yaml") == "ruamel_yaml"

    def test_mixed(self):
        assert _normalize_package_name("My-Package.ext") == "my_package_ext"


class TestStripVersion:
    def test_plain(self):
        assert _strip_version("requests") == "requests"

    def test_version_spec(self):
        assert _strip_version("requests>=2.28") == "requests"

    def test_extras(self):
        assert _strip_version("click[dev]") == "click"

    def test_whitespace(self):
        assert _strip_version("  flask  ") == "flask"


class TestExpectedImportNames:
    def test_simple_package(self):
        assert _expected_import_names("requests") == ["requests"]

    def test_known_mapping(self):
        assert _expected_import_names("Pillow") == ["pil"]

    def test_hyphenated(self):
        assert _expected_import_names("python-dateutil") == ["dateutil"]

    def test_unknown_hyphenated(self):
        assert _expected_import_names("my-package") == ["my_package"]


# ── Python dependency detection ─────────────────────────────────────


class TestPythonDeps:
    def test_pyproject_pep621(self, detector, make_context, tmp_path):
        """Detect unused dep from pyproject.toml PEP 621 dependencies."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests>=2.28", "click"]\n'
        )
        (tmp_path / "app.py").write_text("import click\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "requests" in findings[0].title

    def test_all_used_no_findings(self, detector, make_context, tmp_path):
        """No findings when all deps are imported."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests", "click"]\n'
        )
        (tmp_path / "app.py").write_text("import requests\nimport click\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_known_mapping_pillow(self, detector, make_context, tmp_path):
        """Pillow maps to PIL import."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["Pillow"]\n'
        )
        (tmp_path / "app.py").write_text("from PIL import Image\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_known_mapping_pyyaml(self, detector, make_context, tmp_path):
        """PyYAML maps to yaml import."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["PyYAML"]\n'
        )
        (tmp_path / "app.py").write_text("import yaml\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_tool_packages_skipped(self, detector, make_context, tmp_path):
        """pytest, ruff, mypy etc. are skipped (tool deps, not imported in prod)."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests"]\n'
            '[project.optional-dependencies]\ndev = ["pytest", "ruff", "mypy"]\n'
        )
        (tmp_path / "app.py").write_text("import requests\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_requirements_txt(self, detector, make_context, tmp_path):
        """Parse requirements.txt format."""
        (tmp_path / "requirements.txt").write_text("requests>=2.28\nflask\n")
        (tmp_path / "app.py").write_text("import requests\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "flask" in findings[0].title

    def test_poetry_deps(self, detector, make_context, tmp_path):
        """Parse Poetry-format dependencies."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "^3.10"\n'
            'requests = "^2.28"\nclick = "^8.0"\n'
        )
        (tmp_path / "app.py").write_text("import click\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "requests" in findings[0].title

    def test_from_import(self, detector, make_context, tmp_path):
        """'from X import Y' counts as using X."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests"]\n'
        )
        (tmp_path / "app.py").write_text("from requests import Session\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_subpackage_import(self, detector, make_context, tmp_path):
        """'import foo.bar' counts as using 'foo'."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["google-protobuf"]\n'
        )
        # protobuf maps to google.protobuf → top-level is 'google'
        (tmp_path / "app.py").write_text("import google.protobuf\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_no_python_project(self, detector, make_context, tmp_path):
        """No findings when no Python project markers exist."""
        (tmp_path / "app.py").write_text("import something\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_nested_source_files(self, detector, make_context, tmp_path):
        """Import scanning recurses into subdirectories."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests", "click"]\n'
        )
        src = tmp_path / "src" / "myapp"
        src.mkdir(parents=True)
        (src / "main.py").write_text("import requests\n")
        (src / "cli.py").write_text("import click\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_skips_venv(self, detector, make_context, tmp_path):
        """Files in .venv should not be scanned."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests"]\n'
        )
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "site.py").write_text("import requests\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1  # venv import shouldn't count


# ── JS/TS dependency detection ──────────────────────────────────────


class TestJsDeps:
    def test_package_json_unused(self, detector, make_context, tmp_path):
        """Detect unused dep from package.json."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"express": "^4.0", "lodash": "^4.0"}}'
        )
        (tmp_path / "index.js").write_text(
            "const express = require('express');\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        names = {f.title for f in findings}
        assert "Unused dependency: lodash" in names

    def test_es_module_import(self, detector, make_context, tmp_path):
        """ES module 'import X from' is detected."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "^18.0"}}'
        )
        (tmp_path / "app.tsx").write_text("import React from 'react';\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_scoped_package(self, detector, make_context, tmp_path):
        """Scoped packages like @scope/pkg are handled."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"@tanstack/react-query": "^5.0"}}'
        )
        (tmp_path / "app.ts").write_text(
            "import { useQuery } from '@tanstack/react-query';\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_js_tool_packages_skipped(self, detector, make_context, tmp_path):
        """TypeScript, eslint etc. are skipped."""
        (tmp_path / "package.json").write_text(
            '{"devDependencies": {"typescript": "^5.0", "eslint": "^8.0"}}'
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_dynamic_import(self, detector, make_context, tmp_path):
        """Dynamic import('pkg') is detected."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"lodash": "^4.0"}}'
        )
        (tmp_path / "app.mjs").write_text(
            "const _ = await import('lodash');\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_no_package_json(self, detector, make_context, tmp_path):
        """No findings when no package.json exists."""
        (tmp_path / "index.js").write_text("console.log('hi');\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0


# ── Detector metadata ───────────────────────────────────────────────


class TestDetectorMeta:
    def test_name(self, detector):
        assert detector.name == "unused-deps"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, detector):
        assert "dependency" in detector.categories

    def test_registered(self):
        from sentinel.detectors.base import get_detector
        d = get_detector("unused-deps")
        assert d is not None


# ── False positive awareness ────────────────────────────────────────


class TestFalsePositives:
    def test_comments_with_requirements(self, detector, make_context, tmp_path):
        """Comments and blank lines in requirements.txt are ignored."""
        (tmp_path / "requirements.txt").write_text(
            "# This is a comment\n\nrequests>=2.28\n-e .\n"
        )
        (tmp_path / "app.py").write_text("import requests\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_optional_deps_checked(self, detector, make_context, tmp_path):
        """Optional dependency groups are also checked."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["requests"]\n'
            '[project.optional-dependencies]\nweb = ["flask"]\n'
        )
        (tmp_path / "app.py").write_text("import requests\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "flask" in findings[0].title

    def test_pytest_plugin_prefix_skipped(self, detector, make_context, tmp_path):
        """Pytest plugins (pytest-* prefix) should be skipped (TD-042)."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\n'
            'dependencies = ["pytest-rerunfailures", "pytest-randomly"]\n'
        )
        (tmp_path / "app.py").write_text("pass\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_build_system_requires_excluded(self, detector, make_context, tmp_path):
        """[build-system].requires packages should not be flagged (TD-042)."""
        (tmp_path / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["flit_core>=3.2"]\n'
            'build-backend = "flit_core.buildapi"\n'
            '[project]\nname = "myapp"\n'
            'dependencies = ["flit_core", "requests"]\n'
        )
        (tmp_path / "app.py").write_text("import requests\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        # flit_core should be excluded (in build-system.requires), requests is imported
        assert len(findings) == 0

    def test_build_system_only_excludes_build_deps(self, detector, make_context, tmp_path):
        """Non-build-system deps should still be flagged even if build-system section exists."""
        (tmp_path / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["setuptools"]\n'
            '[project]\nname = "myapp"\n'
            'dependencies = ["requests", "flask"]\n'
        )
        (tmp_path / "app.py").write_text("import requests\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "flask" in findings[0].title

    def test_covdefaults_skipped(self, detector, make_context, tmp_path):
        """Coverage plugins like covdefaults should be skipped (TD-042)."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\n'
            'dependencies = ["covdefaults"]\n'
        )
        (tmp_path / "app.py").write_text("pass\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_type_stubs_skipped(self, detector, make_context, tmp_path):
        """Type stub packages (types-*) should be skipped."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\n'
            'dependencies = ["types-requests", "trio-typing"]\n'
        )
        (tmp_path / "app.py").write_text("pass\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_mkdocs_skipped(self, detector, make_context, tmp_path):
        """Documentation tools like mkdocs should be skipped."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\n'
            'dependencies = ["mkdocs", "mkdocs-material", "twine"]\n'
        )
        (tmp_path / "app.py").write_text("pass\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_js_eslint_config_skipped(self, detector, make_context, tmp_path):
        """JS ESLint config/plugin packages should be skipped."""
        import json
        pkg = {"devDependencies": {
            "eslint-config-turbo": "^1.0",
            "eslint-plugin-tailwindcss": "^3.0",
            "@typescript-eslint/parser": "^6.0",
            "@ianvs/prettier-plugin-sort-imports": "^4.0",
        }}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_js_monorepo_tools_skipped(self, detector, make_context, tmp_path):
        """JS monorepo tools (changesets, commitlint, etc.) should be skipped."""
        import json
        pkg = {"devDependencies": {
            "@changesets/cli": "^2.0",
            "@commitlint/cli": "^17.0",
            "turbo": "^1.0",
            "cross-env": "^7.0",
            "autoprefixer": "^10.0",
        }}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0
