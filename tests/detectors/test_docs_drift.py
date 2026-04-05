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
        assert detector.tier == DetectorTier.LLM_ASSISTED

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

    def test_ignores_suffix_matching_inline_path(self, detector, tmp_path):
        """FP prevention: module-relative path like `store/db.py` that matches
        a file deeper in the repo (e.g. `src/sentinel/store/db.py`)."""
        (tmp_path / "src" / "sentinel" / "store").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "store" / "db.py").write_text("x = 1\n")
        readme = tmp_path / "README.md"
        readme.write_text("Migration logic is in `store/db.py`.\n")

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

    def test_repo_root_relative_links(self, detector, tmp_path):
        """FP prevention: links relative to repo root (common GitHub convention)."""
        (tmp_path / ".github").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("# Guide\n")

        # Link in .github/ uses docs/ which is repo-root relative, not doc-relative
        (tmp_path / ".github" / "instructions.md").write_text(
            "See [guide](docs/guide.md) for details.\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        # Should not flag — docs/guide.md exists at repo root
        link_findings = [f for f in findings if f.context.get("pattern") == "stale-reference"]
        assert len(link_findings) == 0

    def test_ignores_template_paths(self, detector, tmp_path):
        """FP prevention: template/example paths like 'path/to/file.md' should be ignored."""
        readme = tmp_path / "README.md"
        readme.write_text(
            "Format: [text](path/to/file.md)\n"
            "Example: `path/to/your/module.py`\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_ignores_absolute_paths(self, detector, tmp_path):
        """FP prevention: absolute paths describe external systems, not repo files."""
        readme = tmp_path / "README.md"
        readme.write_text(
            "Webhook endpoint: `/hooks/gmail-push`\n"
            "Skills in `/app/skills/` directory.\n"
            "Health at `/health`.\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        inline_path_findings = [
            f for f in findings if f.context and f.context.get("pattern") == "stale-inline-path"
        ]
        assert len(inline_path_findings) == 0


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


class TestDocCodeDrift:
    """Tests for LLM-assisted doc-code comparison (mocked Ollama)."""

    def test_skipped_when_skip_llm(self, detector, tmp_path):
        """LLM comparison is skipped when skip_llm is set."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "sentinel"\n')
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "cli.py").write_text("def main(): pass\n")
        (tmp_path / "README.md").write_text(
            "# Proj\n\n```bash\nsentinel scan .\n```\n"
        )

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"skip_llm": True},
        )
        findings = detector.detect(ctx)
        # No doc-code-drift findings because skip_llm is set
        drift = [f for f in findings if f.context.get("pattern") == "doc-code-drift"]
        assert len(drift) == 0

    def test_skipped_when_ollama_unavailable(self, detector, tmp_path, monkeypatch):
        """LLM comparison gracefully degrades when Ollama is not running."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "sentinel"\n')
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "cli.py").write_text("def main(): pass\n")
        (tmp_path / "README.md").write_text(
            "# Proj\n\n```bash\nsentinel scan .\n```\n"
        )

        from sentinel.detectors import docs_drift

        monkeypatch.setattr(docs_drift, "check_ollama", lambda _: False)

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"skip_llm": False},
        )
        findings = detector.detect(ctx)
        drift = [f for f in findings if f.context.get("pattern") == "doc-code-drift"]
        assert len(drift) == 0

    def test_produces_finding_on_drift(self, detector, tmp_path, monkeypatch):
        """LLM comparison produces a finding when drift is detected."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "sentinel"\n')
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "cli.py").write_text(
            "import click\n\n@click.command()\ndef main(): pass\n"
        )
        (tmp_path / "README.md").write_text(
            "# Proj\n\n```bash\nsentinel scan --format json .\n```\n"
        )

        from sentinel.detectors import docs_drift

        monkeypatch.setattr(docs_drift, "check_ollama", lambda _: True)
        monkeypatch.setattr(
            docs_drift.DocsDriftDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "is_accurate": False,
                "issue": "--format json flag does not exist in the CLI",
            }),
        )

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"skip_llm": False, "model": "test", "ollama_url": "http://fake"},
        )
        findings = detector.detect(ctx)
        drift = [f for f in findings if f.context.get("pattern") == "doc-code-drift"]
        assert len(drift) == 1
        assert drift[0].confidence == 0.65
        assert "--format json" in drift[0].context["llm_issue"]

    def test_no_finding_when_accurate(self, detector, tmp_path, monkeypatch):
        """LLM comparison produces no finding when docs are accurate."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "sentinel"\n')
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "cli.py").write_text(
            "import click\n\n@click.command()\ndef main(): pass\n"
        )
        (tmp_path / "README.md").write_text(
            "# Proj\n\n```bash\nsentinel scan .\n```\n"
        )

        from sentinel.detectors import docs_drift

        monkeypatch.setattr(docs_drift, "check_ollama", lambda _: True)
        monkeypatch.setattr(
            docs_drift.DocsDriftDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {"is_accurate": True, "issue": ""}),
        )

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"skip_llm": False, "model": "test", "ollama_url": "http://fake"},
        )
        findings = detector.detect(ctx)
        drift = [f for f in findings if f.context.get("pattern") == "doc-code-drift"]
        assert len(drift) == 0


class TestPoetryDependencyDrift:
    """Tests for Poetry pyproject.toml dependency format (TD-008)."""

    def test_poetry_deps_not_flagged(self, detector, tmp_path):
        """Packages in [tool.poetry.dependencies] should not be flagged."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "myapp"\nversion = "1.0.0"\n\n'
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'click = "^8.0"\n'
            'httpx = "^0.27"\n'
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install click httpx\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        dep_findings = [f for f in findings if f.context.get("pattern") == "dependency-drift"]
        assert len(dep_findings) == 0

    def test_poetry_missing_dep_flagged(self, detector, tmp_path):
        """Package in docs but not in poetry deps should be flagged."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "myapp"\nversion = "1.0.0"\n\n'
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'click = "^8.0"\n'
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install click flask\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        dep_findings = [f for f in findings if f.context.get("pattern") == "dependency-drift"]
        assert len(dep_findings) == 1
        assert "flask" in dep_findings[0].title.lower()

    def test_poetry_group_deps_not_flagged(self, detector, tmp_path):
        """Packages in [tool.poetry.group.*.dependencies] should not be flagged."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "myapp"\nversion = "1.0.0"\n\n'
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'click = "^8.0"\n\n'
            "[tool.poetry.group.dev.dependencies]\n"
            'pytest = "^8.0"\n'
            'ruff = "^0.4"\n'
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install click pytest ruff\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        dep_findings = [f for f in findings if f.context.get("pattern") == "dependency-drift"]
        assert len(dep_findings) == 0

    def test_python_not_flagged_as_dep(self, detector, tmp_path):
        """'python' in [tool.poetry.dependencies] should be ignored."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "myapp"\nversion = "1.0.0"\n\n'
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
        )
        (tmp_path / "README.md").write_text(
            "## Install\n\n```bash\npip install python\n```\n"
        )

        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        dep_findings = [f for f in findings if f.context.get("pattern") == "dependency-drift"]
        # "python" is not a real pip package name, but the point is that
        # it should not be double-counted from poetry deps
        assert len(dep_findings) == 0
