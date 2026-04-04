"""Tests for the docs-drift detector."""

from __future__ import annotations

import pytest

from sentinel.detectors.docs_drift import DocsDriftDetector
from sentinel.models import DetectorContext, DetectorTier, ScopeType


@pytest.fixture
def detector():
    return DocsDriftDetector()


class TestDocsDriftProperties:
    def test_name(self, detector):
        assert detector.name == "docs-drift"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, detector):
        assert "docs-drift" in detector.categories

    def test_description(self, detector):
        assert detector.description


class TestDocsDriftRegistration:
    def test_registered_in_registry(self):
        from sentinel.detectors.base import get_registry

        registry = get_registry()
        assert "docs-drift" in registry


class TestStaleReferences:
    """True positive and false positive tests for stale reference detection."""

    def test_detects_broken_md_link(self, detector, tmp_path):
        """TP: markdown link to a file that doesn't exist."""
        readme = tmp_path / "README.md"
        readme.write_text("See [guide](docs/guide.md) for details.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)

        assert len(findings) == 1
        assert findings[0].title.startswith("Stale link:")
        assert findings[0].confidence == 0.95
        assert findings[0].context["pattern"] == "stale-reference"

    def test_ignores_valid_md_link(self, detector, tmp_path):
        """FP prevention: link to existing file should not produce a finding."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("# Guide\n")
        readme = tmp_path / "README.md"
        readme.write_text("See [guide](docs/guide.md) for details.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_ignores_external_urls(self, detector, tmp_path):
        """FP prevention: external URLs should not be checked."""
        readme = tmp_path / "README.md"
        readme.write_text(
            "See [GitHub](https://github.com) and "
            "[docs](http://example.com/docs).\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_ignores_anchor_links(self, detector, tmp_path):
        """FP prevention: pure anchor links should not be flagged."""
        readme = tmp_path / "README.md"
        readme.write_text("See [section](#installation) for setup.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_link_with_anchor_checks_file(self, detector, tmp_path):
        """TP: link with anchor where the file doesn't exist."""
        readme = tmp_path / "README.md"
        readme.write_text("See [API docs](docs/api.md#endpoints).\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 1

    def test_link_with_anchor_valid_file(self, detector, tmp_path):
        """FP prevention: link with anchor to existing file."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "api.md").write_text("# API\n## Endpoints\n")
        readme = tmp_path / "README.md"
        readme.write_text("See [API docs](docs/api.md#endpoints).\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_detects_stale_inline_path(self, detector, tmp_path):
        """TP: backtick-quoted path that doesn't exist."""
        readme = tmp_path / "README.md"
        readme.write_text("Config is in `src/config/settings.py`.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert findings[0].context["pattern"] == "stale-inline-path"
        assert findings[0].confidence == 0.80

    def test_ignores_existing_inline_path(self, detector, tmp_path):
        """FP prevention: backtick-quoted path that exists."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "config.py").write_text("x = 1\n")
        readme = tmp_path / "README.md"
        readme.write_text("See `src/config.py` for settings.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_ignores_simple_code_no_path(self, detector, tmp_path):
        """FP prevention: single-word backtick code should not be treated as path."""
        readme = tmp_path / "README.md"
        readme.write_text("Use `pytest` to run tests.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_multiple_stale_links(self, detector, tmp_path):
        """Multiple broken links in one file."""
        readme = tmp_path / "README.md"
        readme.write_text(
            "See [a](missing/a.md) and [b](missing/b.md).\n"
            "Also [c](missing/c.md).\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 3

    def test_scans_nested_docs(self, detector, tmp_path):
        """Scans markdown files in subdirectories."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text(
            "See [api](api/endpoints.md) for details.\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert findings[0].file_path == "docs/guide.md"


class TestDependencyDrift:
    """Tests for dependency drift detection."""

    def test_detects_missing_dep(self, detector, tmp_path):
        """TP: README mentions pip install for a package not in pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = [\n'
            '    "click>=8.0",\n'
            '    "httpx>=0.27",\n'
            "]\n"
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install click httpx flask\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)

        assert len(findings) == 1
        assert "flask" in findings[0].title.lower()
        assert findings[0].context["pattern"] == "dependency-drift"

    def test_no_drift_when_deps_match(self, detector, tmp_path):
        """FP prevention: all doc-mentioned packages exist in project."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = [\n'
            '    "click>=8.0",\n'
            '    "httpx>=0.27",\n'
            "]\n"
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install click httpx\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_ignores_editable_install(self, detector, tmp_path):
        """FP prevention: `pip install -e .` should not flag '.' as missing."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = [\n'
            '    "click>=8.0",\n'
            "]\n"
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install -e .\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_ignores_editable_install_with_extras(self, detector, tmp_path):
        """FP prevention: `pip install -e '.[dev]'` should not flag."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = [\n'
            '    "click>=8.0",\n'
            "]\n"
        )
        (tmp_path / "README.md").write_text(
            '## Install\n\n```bash\npip install -e ".[dev]"\n```\n'
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_handles_requirements_txt(self, detector, tmp_path):
        """Checks requirements.txt if pyproject.toml missing."""
        (tmp_path / "requirements.txt").write_text("click>=8.0\nhttpx>=0.27\n")
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install click httpx requests\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "requests" in findings[0].title.lower()

    def test_handles_package_json(self, detector, tmp_path):
        """Checks package.json for npm projects."""
        import json
        pkg = {"dependencies": {"react": "^18.0.0"}, "devDependencies": {"jest": "^29.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\nnpm install react jest express\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "express" in findings[0].title.lower()

    def test_no_code_blocks_no_findings(self, detector, tmp_path):
        """No install commands in README → no dependency drift findings."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = [\n'
            '    "click>=8.0",\n'
            "]\n"
        )
        (tmp_path / "README.md").write_text("# My App\n\nJust a readme.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        # May find stale links but no dep drift
        dep_findings = [f for f in findings if f.context.get("pattern") == "dependency-drift"]
        assert len(dep_findings) == 0

    def test_optional_deps_not_flagged(self, detector, tmp_path):
        """FP prevention: packages in optional-dependencies should not be flagged."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = [\n'
            '    "click>=8.0",\n'
            "]\n\n"
            "[project.optional-dependencies]\ndev = [\n"
            '    "pytest>=8.0",\n'
            '    "ruff>=0.4",\n'
            "]\n"
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install click pytest\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        dep_findings = [f for f in findings if f.context.get("pattern") == "dependency-drift"]
        assert len(dep_findings) == 0


class TestEmptyRepo:
    def test_no_markdown_no_findings(self, detector, tmp_path):
        """Empty repo with no markdown files."""
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_markdown_no_links(self, detector, tmp_path):
        """Markdown with no links or paths."""
        (tmp_path / "README.md").write_text("# Hello World\n\nJust text.\n")

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0


class TestScopeFiltering:
    def test_targeted_scope(self, detector, tmp_path):
        """Only scans targeted files."""
        (tmp_path / "README.md").write_text("See [a](missing.md).\n")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("See [b](missing2.md).\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.TARGETED,
            target_paths=["README.md"],
        )
        findings = detector.detect(ctx)
        # Only README.md should be scanned
        assert all(f.file_path == "README.md" for f in findings)

    def test_incremental_scope(self, detector, tmp_path):
        """Only scans changed files in incremental mode."""
        (tmp_path / "README.md").write_text("See [a](missing.md).\n")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("See [b](missing2.md).\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["docs/guide.md"],
        )
        findings = detector.detect(ctx)
        assert all(f.file_path == "docs/guide.md" for f in findings)
