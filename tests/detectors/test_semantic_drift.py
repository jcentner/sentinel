"""Tests for the semantic docs-drift detector."""

from __future__ import annotations

import pytest

from sentinel.core.extractors import extract_signatures
from sentinel.detectors.semantic_drift import (
    SemanticDriftDetector,
    _extract_code_excerpt,
    _extract_symbols,
    _match_symbols_to_files,
    extract_code_pairs,
    parse_sections,
)
from sentinel.models import DetectorContext, DetectorTier, ScopeType


@pytest.fixture
def detector():
    return SemanticDriftDetector()


# ── Detector properties ───────────────────────────────────────────


class TestSemanticDriftProperties:
    def test_name(self, detector):
        assert detector.name == "semantic-drift"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.LLM_ASSISTED

    def test_categories(self, detector):
        assert "docs-drift" in detector.categories

    def test_description(self, detector):
        assert detector.description


class TestSemanticDriftRegistration:
    def test_registered_in_registry(self):
        from sentinel.detectors.base import get_registry

        registry = get_registry()
        assert "semantic-drift" in registry


# ── Section parsing ───────────────────────────────────────────────


class TestParseSections:
    def test_basic_heading_split(self):
        content = (
            "# Introduction\n\n"
            "This is the introduction section with enough text to pass the minimum length filter.\n\n"
            "## Installation\n\n"
            "Run pip install to get started with the project and all its dependencies.\n\n"
            "## Usage\n\n"
            "Use sentinel scan to run a scan on your repository and get results.\n"
        )
        sections = parse_sections(content)
        assert len(sections) == 3
        assert sections[0]["title"] == "Introduction"
        assert sections[1]["title"] == "Installation"
        assert sections[2]["title"] == "Usage"

    def test_line_numbers(self):
        content = (
            "# First\n\n"
            "Body text for the first section which must be long enough to pass.\n\n"
            "## Second\n\n"
            "Body text for the second section which must also be long enough for the test.\n"
        )
        sections = parse_sections(content)
        assert len(sections) == 2
        assert sections[0]["line_start"] == 1  # 1-indexed
        assert sections[1]["line_start"] == 5

    def test_filters_short_sections(self):
        content = (
            "# Title\n\n"
            "Short.\n\n"
            "## Real Section\n\n"
            "This section has enough text to pass the minimum character threshold for analysis.\n"
        )
        sections = parse_sections(content)
        assert len(sections) == 1
        assert sections[0]["title"] == "Real Section"

    def test_h3_headings_included(self):
        content = (
            "### Subsection\n\n"
            "This is a subsection with enough body text to pass the filter for minimum length.\n"
        )
        sections = parse_sections(content)
        assert len(sections) == 1
        assert sections[0]["level"] == 3

    def test_h4_headings_ignored(self):
        content = (
            "#### Too Deep\n\n"
            "This section uses h4 which is too deep to be parsed and should be ignored entirely.\n"
        )
        sections = parse_sections(content)
        assert len(sections) == 0

    def test_empty_content(self):
        assert parse_sections("") == []

    def test_no_headings(self):
        content = "Just some text without any headings in the document at all.\n"
        assert parse_sections(content) == []

    def test_body_excludes_heading_line(self):
        content = "# Title\n\nBody text that is long enough to pass the minimum length filter for section.\n"
        sections = parse_sections(content)
        assert "# Title" not in sections[0]["body"]
        assert "Body text" in sections[0]["body"]


# ── Reference extraction ──────────────────────────────────────────


class TestExtractCodePairs:
    def test_backtick_path(self, tmp_path):
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        code_file = tmp_path / "src" / "sentinel" / "config.py"
        code_file.write_text("class SentinelConfig:\n    model: str = 'qwen'\n")

        section = {
            "title": "Configuration",
            "body": "Edit `src/sentinel/config.py` to change settings for the project.",
            "line_start": 1,
            "line_end": 3,
        }
        pairs = extract_code_pairs(section, tmp_path)
        assert len(pairs) == 1
        assert pairs[0][0] == "src/sentinel/config.py"

    def test_prose_path(self, tmp_path):
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        code_file = tmp_path / "src" / "sentinel" / "runner.py"
        code_file.write_text("def run_scan():\n    pass\n")

        section = {
            "title": "Pipeline",
            "body": "The main pipeline is in src/sentinel/runner.py which orchestrates everything.",
            "line_start": 1,
            "line_end": 3,
        }
        pairs = extract_code_pairs(section, tmp_path)
        assert len(pairs) == 1
        assert pairs[0][0] == "src/sentinel/runner.py"

    def test_markdown_link_path(self, tmp_path):
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        code_file = tmp_path / "src" / "sentinel" / "cli.py"
        code_file.write_text("import click\n\ndef main():\n    pass\n")

        section = {
            "title": "CLI",
            "body": "The CLI entry point is [cli.py](src/sentinel/cli.py) which handles all commands.",
            "line_start": 1,
            "line_end": 3,
        }
        pairs = extract_code_pairs(section, tmp_path)
        assert len(pairs) == 1
        assert pairs[0][0] == "src/sentinel/cli.py"

    def test_nonexistent_path_skipped(self, tmp_path):
        section = {
            "title": "Missing",
            "body": "See `src/sentinel/nonexistent.py` for details about this feature.",
            "line_start": 1,
            "line_end": 3,
        }
        pairs = extract_code_pairs(section, tmp_path)
        assert len(pairs) == 0

    def test_skip_dirs_respected(self, tmp_path):
        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / "node_modules" / "pkg" / "index.js").write_text("module.exports = {};\n")

        section = {
            "title": "Deps",
            "body": "See `node_modules/pkg/index.js` for the vendored dependency code.",
            "line_start": 1,
            "line_end": 3,
        }
        pairs = extract_code_pairs(section, tmp_path)
        assert len(pairs) == 0

    def test_deduplicates_paths(self, tmp_path):
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "config.py").write_text("x = 1\n")

        section = {
            "title": "Config",
            "body": (
                "Edit `src/sentinel/config.py` — the config is in "
                "src/sentinel/config.py and also linked [here](src/sentinel/config.py)."
            ),
            "line_start": 1,
            "line_end": 3,
        }
        pairs = extract_code_pairs(section, tmp_path)
        assert len(pairs) == 1


class TestExtractSymbols:
    def test_function_names(self):
        body = "Call `run_scan()` to start the pipeline and `generate_report()` for output."
        symbols = _extract_symbols(body)
        assert "run_scan" in symbols
        assert "generate_report" in symbols

    def test_class_names(self):
        body = "The `SentinelConfig` class holds all configuration values for the system."
        symbols = _extract_symbols(body)
        assert "SentinelConfig" in symbols

    def test_filters_keywords(self):
        body = "Returns `True` or `False` and accepts a `str` parameter for the input."
        symbols = _extract_symbols(body)
        assert len(symbols) == 0

    def test_filters_short_names(self):
        body = "The `db` and `id` fields are used internally by the store layer."
        symbols = _extract_symbols(body)
        assert len(symbols) == 0


class TestMatchSymbolsToFiles:
    def test_finds_function_definition(self, tmp_path):
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "runner.py").write_text(
            "def run_scan():\n    pass\n"
        )
        pairs = _match_symbols_to_files(["run_scan"], tmp_path)
        assert len(pairs) == 1
        assert "runner.py" in pairs[0][0]

    def test_finds_class_definition(self, tmp_path):
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "config.py").write_text(
            "class SentinelConfig:\n    model: str = 'qwen'\n"
        )
        pairs = _match_symbols_to_files(["SentinelConfig"], tmp_path)
        assert len(pairs) == 1
        assert "config.py" in pairs[0][0]

    def test_no_match_returns_empty(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "empty.py").write_text("x = 1\n")
        pairs = _match_symbols_to_files(["NonExistentClass"], tmp_path)
        assert len(pairs) == 0

    def test_limits_to_3_matches(self, tmp_path):
        (tmp_path / "src").mkdir()
        for i in range(5):
            (tmp_path / "src" / f"mod{i}.py").write_text(f"def target_fn():\n    return {i}\n")
        pairs = _match_symbols_to_files(["target_fn"], tmp_path)
        assert len(pairs) <= 3


# ── Python code extraction ────────────────────────────────────────


class TestExtractPythonSignatures:
    def test_extracts_function_signatures(self):
        source = (
            'def run_scan(repo_path: str, model: str = "qwen") -> list:\n'
            '    """Run a full scan on the repo."""\n'
            "    pass\n\n"
            "def helper():\n"
            "    pass\n"
        )
        result = extract_signatures(source, "python")
        assert "run_scan" in result
        assert "helper" in result

    def test_extracts_class_signatures(self):
        source = (
            "class Config:\n"
            '    """Configuration class."""\n'
            "    def __init__(self):\n"
            "        pass\n"
            "    def load(self):\n"
            "        pass\n"
        )
        result = extract_signatures(source, "python")
        assert "class Config" in result
        assert "__init__" in result
        assert "load" in result

    def test_includes_docstrings(self):
        source = (
            "def example():\n"
            '    """This function does a specific thing."""\n'
            "    return 42\n"
        )
        result = extract_signatures(source, "python")
        assert "specific thing" in result

    def test_handles_syntax_error(self):
        source = "def broken(\n    # missing close paren\n"
        result = extract_signatures(source, "python")
        assert result is not None  # falls back to first lines

    def test_empty_file(self):
        result = extract_signatures("", "python")
        # Empty file has no functions — returns first lines (empty)
        assert result is not None


class TestExtractCodeExcerpt:
    def test_python_file(self, tmp_path):
        py_file = tmp_path / "test.py"
        py_file.write_text("def hello():\n    return 'world'\n")
        excerpt = _extract_code_excerpt(py_file)
        assert "hello" in excerpt

    def test_js_file(self, tmp_path):
        js_file = tmp_path / "index.js"
        js_file.write_text("function hello() {\n  return 'world';\n}\n")
        excerpt = _extract_code_excerpt(js_file)
        assert "hello" in excerpt

    def test_empty_file_returns_none(self, tmp_path):
        empty = tmp_path / "empty.py"
        empty.write_text("")
        assert _extract_code_excerpt(empty) is None

    def test_nonexistent_file_returns_none(self, tmp_path):
        assert _extract_code_excerpt(tmp_path / "nope.py") is None


# ── Detector integration ──────────────────────────────────────────


class TestDetectorIntegration:
    def test_skip_llm_returns_empty(self, detector, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# Usage\n\nSee `src/sentinel/cli.py` for the CLI entry point.\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"skip_llm": True},
        )
        findings = detector.detect(ctx)
        assert findings == []

    def test_ollama_unavailable_returns_empty(self, detector, tmp_path):
        """When provider health check fails, detector returns empty."""
        from tests.mock_provider import MockProvider

        readme = tmp_path / "README.md"
        readme.write_text("# Usage\n\nSee `src/sentinel/cli.py` for the CLI entry point.\n")

        provider = MockProvider(health=False)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": provider},
        )
        findings = detector.detect(ctx)
        assert findings == []

    def test_no_key_docs_returns_empty(self, detector, tmp_path):
        # Only non-key docs present
        (tmp_path / "random-notes.md").write_text("# Notes\n\nSome random content.\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"skip_llm": True},
        )
        findings = detector.detect(ctx)
        assert findings == []

    def test_produces_finding_on_drift(self, detector, tmp_path, monkeypatch):
        """Integration test with mocked LLM returning a drift signal."""
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "config.py").write_text(
            "class SentinelConfig:\n"
            "    model: str = 'qwen3.5:4b'\n"
            "    ollama_url: str = 'http://localhost:11434'\n"
        )
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Configuration\n\n"
            "Edit `src/sentinel/config.py` to change the default model. "
            "The default model is gpt-4 and requires an OpenAI API key.\n"
        )

        from sentinel.detectors import semantic_drift

        monkeypatch.setattr(
            semantic_drift.SemanticDriftDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": True,
                "reason": "Doc says gpt-4 but code uses qwen3.5:4b",
            }),
        )

        from tests.mock_provider import MockProvider
        provider = MockProvider(health=True)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": provider},
        )
        findings = detector.detect(ctx)

        assert len(findings) == 1
        f = findings[0]
        assert f.detector == "semantic-drift"
        assert f.category == "docs-drift"
        assert f.confidence == 0.6
        assert "Configuration" in f.title
        assert "config.py" in f.title
        assert len(f.evidence) == 2
        assert f.context["pattern"] == "semantic-drift"

    def test_no_finding_when_in_sync(self, detector, tmp_path, monkeypatch):
        """When LLM says docs are accurate, no finding is produced."""
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "config.py").write_text(
            "class SentinelConfig:\n    model: str = 'qwen3.5:4b'\n"
        )
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Configuration\n\n"
            "Edit `src/sentinel/config.py` to change the default model (qwen3.5:4b via Ollama).\n"
        )

        from sentinel.detectors import semantic_drift

        monkeypatch.setattr(
            semantic_drift.SemanticDriftDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {"needs_review": False, "reason": ""}),
        )

        from tests.mock_provider import MockProvider
        provider = MockProvider(health=True)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": provider},
        )
        findings = detector.detect(ctx)

        assert findings == []

    def test_handles_llm_parse_failure(self, detector, tmp_path, monkeypatch):
        """When LLM returns None (unparseable), no finding is produced."""
        (tmp_path / "src" / "sentinel").mkdir(parents=True)
        (tmp_path / "src" / "sentinel" / "config.py").write_text("x = 1\n")
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Configuration\n\n"
            "Edit `src/sentinel/config.py` to change settings for the configuration system.\n"
        )

        from sentinel.detectors import semantic_drift

        monkeypatch.setattr(
            semantic_drift.SemanticDriftDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: None),
        )

        from tests.mock_provider import MockProvider
        provider = MockProvider(health=True)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": provider},
        )
        findings = detector.detect(ctx)

        assert findings == []

    def test_targeted_scope_filters_non_key_docs(self, detector, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# Title\n\nContent here.\n")
        notes = tmp_path / "notes.md"
        notes.write_text("# Notes\n\nRandom notes.\n")

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.TARGETED,
            target_paths=["notes.md"],
            config={"skip_llm": True},
        )
        findings = detector.detect(ctx)
        assert findings == []

    def test_finds_docs_in_docs_directory(self, detector, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        usage = docs_dir / "USAGE.md"
        usage.write_text("# Usage\n\nSome usage information.\n")

        found = detector._get_key_docs(
            DetectorContext(repo_root=str(tmp_path)), tmp_path
        )
        assert len(found) == 1
        assert found[0].name == "USAGE.md"


# ── Key doc discovery ─────────────────────────────────────────────


class TestGetKeyDocs:
    def test_finds_readme(self, detector, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n")
        found = detector._get_key_docs(
            DetectorContext(repo_root=str(tmp_path)), tmp_path
        )
        assert len(found) == 1
        assert found[0].name == "README.md"

    def test_finds_contributing(self, detector, tmp_path):
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n")
        found = detector._get_key_docs(
            DetectorContext(repo_root=str(tmp_path)), tmp_path
        )
        assert len(found) == 1

    def test_ignores_non_key_docs(self, detector, tmp_path):
        (tmp_path / "random.md").write_text("# Random\n")
        found = detector._get_key_docs(
            DetectorContext(repo_root=str(tmp_path)), tmp_path
        )
        assert len(found) == 0

    def test_targeted_scope(self, detector, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n")
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.TARGETED,
            target_paths=["README.md"],
        )
        found = detector._get_key_docs(ctx, tmp_path)
        assert len(found) == 1

    def test_incremental_scope_filters_unchanged(self, detector, tmp_path):
        """Incremental scope only returns changed key docs."""
        (tmp_path / "README.md").write_text("# Project\n")
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n")
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["README.md"],
        )
        found = detector._get_key_docs(ctx, tmp_path)
        assert len(found) == 1
        assert found[0].name == "README.md"

    def test_incremental_scope_ignores_non_key_changed(self, detector, tmp_path):
        """Changed files that aren't key docs are excluded."""
        (tmp_path / "notes.md").write_text("# Notes\n")
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["notes.md"],
        )
        found = detector._get_key_docs(ctx, tmp_path)
        assert len(found) == 0


# ── Enhanced mode tests ──────────────────────────────────────────


class TestEnhancedSemanticDrift:
    """Test enhanced mode for standard+ model capability."""

    def test_capability_tier_is_basic(self):
        from sentinel.models import CapabilityTier

        d = SemanticDriftDetector()
        assert d.capability_tier == CapabilityTier.BASIC

    def test_enhanced_finding_has_specifics(self, tmp_path):
        """When model_capability=standard, findings include specific inaccuracies."""
        from unittest.mock import MagicMock

        from sentinel.core.provider import LLMResponse
        from sentinel.models import DetectorContext

        mock_provider = MagicMock()
        mock_provider.check_health.return_value = True
        mock_provider.generate.return_value = LLMResponse(
            text='{"needs_review": true, "severity": "high", '
            '"reason": "Function signature changed", '
            '"specifics": ["Docs say run_scan(path) but actual signature is run_scan(path, conn)", '
            '"Missing skip_judge parameter in docs"]}',
            token_count=80,
            duration_ms=200.0,
        )

        # Create a key doc and source file it references
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Usage\n\n"
            "Run a scan with `run_scan(path)` to analyze your repo.\n"
            "The function returns a report.\n"
            "See `src/scanner.py` for implementation details.\n"
        )
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "scanner.py").write_text(
            "def run_scan(path, conn, *, skip_judge=False):\n"
            "    '''Run a full scan.'''\n"
            "    return 'report'\n"
        )

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "provider": mock_provider,
                "skip_llm": False,
                "num_ctx": 2048,
                "model_capability": "standard",
            },
        )

        d = SemanticDriftDetector()
        findings = d.detect(ctx)

        assert len(findings) >= 1
        f = findings[0]
        assert f.confidence == 0.75
        assert f.severity.value == "high"
        assert "Function signature changed" in f.description
        assert f.context["enhanced"] is True
        assert len(f.context["specifics"]) == 2

    def test_basic_mode_no_specifics(self, tmp_path):
        """When model_capability=basic, findings use binary signal only."""
        from unittest.mock import MagicMock

        from sentinel.core.provider import LLMResponse
        from sentinel.models import DetectorContext

        mock_provider = MagicMock()
        mock_provider.check_health.return_value = True
        mock_provider.generate.return_value = LLMResponse(
            text='{"needs_review": true, "reason": "Docs are outdated"}',
            token_count=30,
            duration_ms=100.0,
        )

        readme = tmp_path / "README.md"
        readme.write_text(
            "# API\n\n"
            "Use `process(data)` to transform input.\n"
            "See `src/processor.py` for the implementation.\n"
        )
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "processor.py").write_text(
            "def process(data, *, verbose=False):\n"
            "    '''Process the data.'''\n"
            "    return data\n"
        )

        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "provider": mock_provider,
                "skip_llm": False,
                "num_ctx": 2048,
                "model_capability": "basic",
            },
        )

        d = SemanticDriftDetector()
        findings = d.detect(ctx)

        assert len(findings) >= 1
        f = findings[0]
        assert f.confidence == 0.6
        assert "enhanced" not in f.context


# ── JS/TS multi-language support ─────────────────────────────────


class TestExtractCodeExcerptJS:
    def test_ts_file(self, tmp_path):
        ts_file = tmp_path / "index.ts"
        ts_file.write_text(
            "export function hello(): string {\n"
            "    return 'world';\n"
            "}\n"
            "\n"
            "export function goodbye(): void {\n"
            "    console.log('bye');\n"
            "}\n"
        )
        excerpt = _extract_code_excerpt(ts_file)
        assert excerpt is not None
        assert "hello" in excerpt

    def test_js_file(self, tmp_path):
        js_file = tmp_path / "utils.js"
        js_file.write_text(
            "function validate(input) {\n"
            "    return input.trim().length > 0;\n"
            "}\n"
            "\n"
            "function format(str) {\n"
            "    return str.toUpperCase();\n"
            "}\n"
        )
        excerpt = _extract_code_excerpt(js_file)
        assert excerpt is not None
        assert "validate" in excerpt


class TestMatchSymbolsToFilesJS:
    def test_finds_js_function_definition(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "runner.js").write_text(
            "function runScan() {\n"
            "    return [];\n"
            "}\n"
        )
        pairs = _match_symbols_to_files(["runScan"], tmp_path)
        assert len(pairs) == 1
        assert "runner.js" in pairs[0][0]

    def test_finds_ts_function_definition(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "config.ts").write_text(
            "export function loadConfig(): any {\n"
            "    return {};\n"
            "}\n"
        )
        pairs = _match_symbols_to_files(["loadConfig"], tmp_path)
        assert len(pairs) == 1
        assert "config.ts" in pairs[0][0]


class TestDetectorIntegrationJS:
    def test_produces_finding_on_drift_js(self, tmp_path, monkeypatch):
        """Drift between markdown docs and JS/TS source file."""
        from sentinel.detectors import semantic_drift
        from tests.mock_provider import MockProvider

        src = tmp_path / "src"
        src.mkdir()
        (src / "config.ts").write_text(
            "export const defaultModel = 'qwen3.5:4b';\n"
            "export const apiUrl = 'http://localhost:11434';\n"
        )

        readme = tmp_path / "README.md"
        readme.write_text(
            "# Configuration\n\n"
            "Edit `src/config.ts` to change the default model.\n"
            "The default model is gpt-4 and requires an OpenAI API key.\n"
        )

        monkeypatch.setattr(
            semantic_drift.SemanticDriftDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": True,
                "reason": "README says gpt-4 but code uses qwen3.5",
            }),
        )

        d = SemanticDriftDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": MockProvider(health=True)},
        )
        findings = d.detect(ctx)
        drift = [f for f in findings if f.category == "docs-drift"]
        assert len(drift) >= 1

    def test_no_finding_when_consistent_js(self, tmp_path, monkeypatch):
        """Well-documented JS/TS codebase produces no findings."""
        from sentinel.detectors import semantic_drift
        from tests.mock_provider import MockProvider

        src = tmp_path / "src"
        src.mkdir()
        (src / "utils.ts").write_text(
            "export function validate(input: string): boolean {\n"
            "    return input.trim().length > 0;\n"
            "}\n"
        )

        readme = tmp_path / "README.md"
        readme.write_text(
            "# Utils\n\n"
            "The `validate()` function checks that the input\n"
            "is non-empty after trimming whitespace.\n"
        )

        monkeypatch.setattr(
            semantic_drift.SemanticDriftDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": False,
                "reason": "",
            }),
        )

        d = SemanticDriftDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": MockProvider(health=True)},
        )
        findings = d.detect(ctx)
        assert len(findings) == 0
