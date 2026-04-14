"""Tests for the inline comment drift detector."""

from __future__ import annotations

import pytest

from sentinel.core.extractors import has_tree_sitter
from sentinel.detectors.inline_comment_drift import (
    InlineCommentDrift,
    _sort_by_risk,
    extract_docstring_pairs,
)
from sentinel.models import DetectorContext, DetectorTier, ScopeType

_skip_no_tree_sitter = pytest.mark.skipif(
    not has_tree_sitter(), reason="tree-sitter not installed",
)


@pytest.fixture
def detector():
    return InlineCommentDrift()


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
        assert detector.name == "inline-comment-drift"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.LLM_ASSISTED

    def test_categories(self, detector):
        assert "docs-drift" in detector.categories

    def test_capability_tier(self, detector):
        from sentinel.models import CapabilityTier
        assert detector.capability_tier == CapabilityTier.BASIC

    def test_registered(self):
        from sentinel.detectors.base import get_registry
        registry = get_registry()
        assert "inline-comment-drift" in registry


# ── AST extraction ──────────────────────────────────────────────────


class TestExtractDocstringPairs:
    def test_function_with_docstring(self):
        source = (
            "def greet(name):\n"
            '    """Say hello to the given name and return a greeting string."""\n'
            '    return f"Hello, {name}!"\n'
        )
        pairs = extract_docstring_pairs(source)
        assert len(pairs) == 1
        assert pairs[0]["name"] == "greet"
        assert "Say hello" in pairs[0]["docstring"]
        assert "Hello" in pairs[0]["code"]

    def test_class_with_docstring(self):
        source = (
            "class Calculator:\n"
            '    """A calculator that adds and subtracts numbers."""\n'
            "    def add(self, a, b):\n"
            "        return a + b\n"
        )
        pairs = extract_docstring_pairs(source)
        names = {p["name"] for p in pairs}
        assert "Calculator" in names

    def test_async_function(self):
        source = (
            "async def fetch_data(url):\n"
            '    """Fetch data from the given URL and return JSON."""\n'
            "    response = await client.get(url)\n"
            "    return response.json()\n"
        )
        pairs = extract_docstring_pairs(source)
        assert len(pairs) == 1
        assert pairs[0]["name"] == "fetch_data"

    def test_skips_short_docstring(self):
        source = (
            "def f():\n"
            '    """Short."""\n'
            "    return 1\n"
        )
        pairs = extract_docstring_pairs(source)
        assert len(pairs) == 0  # below _MIN_DOCSTRING_CHARS

    def test_skips_no_body(self):
        source = (
            "def f():\n"
            '    """This docstring has enough chars to be processed ok."""\n'
        )
        pairs = extract_docstring_pairs(source)
        assert len(pairs) == 0  # no body beyond docstring

    def test_skips_syntax_error(self):
        source = "def f(\n"
        pairs = extract_docstring_pairs(source)
        assert pairs == []

    def test_no_docstring(self):
        source = (
            "def f():\n"
            "    return 42\n"
        )
        pairs = extract_docstring_pairs(source)
        assert len(pairs) == 0

    def test_line_numbers(self):
        source = (
            "# comment\n"
            "def greet(name):\n"
            '    """Say hello to the given name. This is long enough."""\n'
            '    return f"Hello, {name}!"\n'
        )
        pairs = extract_docstring_pairs(source)
        assert len(pairs) == 1
        assert pairs[0]["line_start"] == 2
        assert pairs[0]["code_start"] == 4
        assert pairs[0]["code_end"] == 4


# ── Detector behavior ──────────────────────────────────────────────


class TestDetectorBehavior:
    def test_skip_llm_flag(self, detector, make_context, tmp_path):
        """skip_llm disables the detector."""
        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Hello, {name}!"\n'
        )
        ctx = make_context(config={"skip_llm": True})
        findings = detector.detect(ctx)
        assert findings == []

    def test_no_provider(self, detector, make_context, tmp_path):
        """No provider means no findings."""
        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Hello, {name}!"\n'
        )
        ctx = make_context(config={})
        findings = detector.detect(ctx)
        assert findings == []

    def test_unhealthy_provider(self, detector, make_context, tmp_path):
        """Unhealthy provider means no findings."""
        from tests.mock_provider import MockProvider

        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Hello, {name}!"\n'
        )
        provider = MockProvider(health=False)
        ctx = make_context(config={"provider": provider})
        findings = detector.detect(ctx)
        assert findings == []

    def test_finding_when_drift_detected(self, detector, tmp_path, monkeypatch):
        """LLM flagging a docstring produces a finding."""
        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Goodbye, {name}!"\n'
        )

        from sentinel.detectors import inline_comment_drift

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": True,
                "reason": "Docstring says hello but code says goodbye",
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
        assert f.detector == "inline-comment-drift"
        assert f.category == "docs-drift"
        assert f.confidence == 0.55  # basic mode
        assert "greet" in f.title
        assert "mod.py" in f.title
        assert f.file_path == "mod.py"
        assert len(f.evidence) == 2
        assert f.context["pattern"] == "inline-comment-drift"
        assert f.context["symbol_name"] == "greet"

    def test_no_finding_when_in_sync(self, detector, tmp_path, monkeypatch):
        """LLM saying in-sync produces no finding."""
        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Hello, {name}!"\n'
        )

        from sentinel.detectors import inline_comment_drift

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": False, "reason": "",
            }),
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
        """LLM returning None (unparseable) is handled gracefully."""
        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Hello, {name}!"\n'
        )

        from sentinel.detectors import inline_comment_drift

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
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

    def test_exception_returns_empty(self, detector, make_context, tmp_path, monkeypatch):
        """Exceptions in detect() are caught and return empty list."""
        monkeypatch.setattr(
            detector, "_scan", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert findings == []

    def test_incremental_scope(self, detector, tmp_path, monkeypatch):
        """Only changed files are scanned in incremental mode."""
        (tmp_path / "changed.py").write_text(
            "def changed_func():\n"
            '    """This function was changed recently and is long enough."""\n'
            "    return 42\n"
        )
        (tmp_path / "unchanged.py").write_text(
            "def unchanged_func():\n"
            '    """This function was not changed and is long enough text."""\n'
            "    return 0\n"
        )

        from sentinel.detectors import inline_comment_drift

        calls: list[str] = []

        def mock_compare(*args, **kwargs):
            # args[1] is code, args[2] is file_path
            calls.append(args[2])
            return {"needs_review": False, "reason": ""}

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
            "_llm_compare",
            staticmethod(mock_compare),
        )

        from tests.mock_provider import MockProvider
        provider = MockProvider(health=True)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["changed.py"],
            config={"provider": provider},
        )
        detector.detect(ctx)

        assert "changed.py" in calls
        assert "unchanged.py" not in calls


# ── Risk-based sorting ──────────────────────────────────────────────


class TestRiskSorting:
    def test_sorts_by_risk(self, tmp_path):
        """Files are sorted by risk score (highest first)."""
        (tmp_path / "low.py").write_text("")
        (tmp_path / "high.py").write_text("")
        files = [tmp_path / "low.py", tmp_path / "high.py"]
        signals = {
            "low.py": {"churn_commits": 2, "churn_fix_ratio": 0.1},
            "high.py": {"churn_commits": 15, "churn_fix_ratio": 0.5},
        }
        sorted_files = _sort_by_risk(files, tmp_path, signals)
        assert sorted_files[0].name == "high.py"
        assert sorted_files[1].name == "low.py"

    def test_missing_risk_defaults_to_zero(self, tmp_path):
        """Files without risk signals sort last."""
        (tmp_path / "known.py").write_text("")
        (tmp_path / "unknown.py").write_text("")
        files = [tmp_path / "unknown.py", tmp_path / "known.py"]
        signals = {"known.py": {"churn_commits": 5, "churn_fix_ratio": 0.0}}
        sorted_files = _sort_by_risk(files, tmp_path, signals)
        assert sorted_files[0].name == "known.py"


# ── Finding structure ───────────────────────────────────────────────


class TestFindingStructure:
    def test_enhanced_mode_confidence(self, detector, tmp_path, monkeypatch):
        """Enhanced mode produces higher confidence."""
        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Goodbye, {name}!"\n'
        )

        from sentinel.detectors import inline_comment_drift

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": True,
                "reason": "Docstring says hello but code says goodbye",
                "severity": "high",
            }),
        )

        from tests.mock_provider import MockProvider
        provider = MockProvider(health=True)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={
                "provider": provider,
                "model_capability": "standard",
            },
        )
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert findings[0].confidence == 0.70
        assert findings[0].severity.value == "high"
        assert findings[0].context.get("enhanced") is True


# ── JS/TS multi-language support ────────────────────────────────────


@_skip_no_tree_sitter
class TestExtractDocstringPairsJS:
    """JSDoc extraction via extract_docstring_pairs."""

    def test_jsdoc_function(self):
        source = (
            "/**\n"
            " * Format a user greeting with their full name and title.\n"
            " * @param {string} name - The user's name\n"
            " * @returns {string} Formatted greeting\n"
            " */\n"
            "function greet(name) {\n"
            "    return `Goodbye, ${name}!`;\n"
            "}\n"
        )
        pairs = extract_docstring_pairs(source, language="javascript")
        assert len(pairs) == 1
        assert pairs[0]["name"] == "greet"
        assert "greeting" in pairs[0]["docstring"].lower()

    def test_ts_function_with_jsdoc(self):
        source = (
            "/**\n"
            " * Process records with validation and transformation.\n"
            " * Applies strict schema checks on all input records.\n"
            " */\n"
            "export function processRecords(records: any[]): any {\n"
            "    return records.filter(r => r.id);\n"
            "}\n"
        )
        pairs = extract_docstring_pairs(source, language="typescript")
        assert len(pairs) == 1
        assert pairs[0]["name"] == "processRecords"

    def test_no_jsdoc_js(self):
        source = (
            "function helper(x) {\n"
            "    return x + 1;\n"
            "}\n"
        )
        pairs = extract_docstring_pairs(source, language="javascript")
        assert len(pairs) == 0


@_skip_no_tree_sitter
class TestDetectorBehaviorJS:
    def test_finding_when_drift_detected_js(self, detector, tmp_path, monkeypatch):
        """LLM flagging a JSDoc produces a finding on a .js file."""
        (tmp_path / "utils.js").write_text(
            "/**\n"
            " * Format a user greeting with their full name and title.\n"
            " * @param {string} name - The user's name\n"
            " * @returns {string} Formatted greeting\n"
            " */\n"
            "function greet(name) {\n"
            "    return `Goodbye, ${name}!`;\n"
            "}\n"
        )

        from sentinel.detectors import inline_comment_drift

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": True,
                "reason": "JSDoc says greeting but code says goodbye",
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
        assert f.file_path == "utils.js"
        assert "greet" in f.title

    def test_incremental_scope_ts(self, detector, tmp_path, monkeypatch):
        """Only changed .ts files are scanned in incremental mode."""
        (tmp_path / "changed.ts").write_text(
            "/**\n"
            " * This function was changed recently and is long enough.\n"
            " * It does some important processing for the application.\n"
            " */\n"
            "export function changedFunc(): number {\n"
            "    return 42;\n"
            "}\n"
        )
        (tmp_path / "unchanged.ts").write_text(
            "/**\n"
            " * This function was not changed and is also long enough.\n"
            " * It handles other tasks in the system entirely.\n"
            " */\n"
            "export function unchangedFunc(): number {\n"
            "    return 0;\n"
            "}\n"
        )

        from sentinel.detectors import inline_comment_drift

        calls: list[str] = []

        def mock_compare(*args, **kwargs):
            calls.append(args[2])  # file_path argument
            return {"needs_review": False, "reason": ""}

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
            "_llm_compare",
            staticmethod(mock_compare),
        )

        from tests.mock_provider import MockProvider
        provider = MockProvider(health=True)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["changed.ts"],
            config={"provider": provider},
        )
        detector.detect(ctx)

        assert "changed.ts" in calls
        assert "unchanged.ts" not in calls

    def test_mixed_language_repo(self, detector, tmp_path, monkeypatch):
        """Both Python and JS files are discovered and scanned."""
        (tmp_path / "mod.py").write_text(
            "def greet(name):\n"
            '    """Say hello to the given name. This has enough text."""\n'
            '    return f"Hello, {name}!"\n'
        )
        (tmp_path / "utils.js").write_text(
            "/**\n"
            " * Format a user greeting with their full name and title.\n"
            " * @param {string} name - The user's name\n"
            " * @returns {string} Formatted greeting\n"
            " */\n"
            "function greet(name) {\n"
            "    return `Hello, ${name}!`;\n"
            "}\n"
        )

        from sentinel.detectors import inline_comment_drift

        scanned_files: list[str] = []

        def mock_compare(*args, **kwargs):
            scanned_files.append(args[2])  # file_path argument
            return {"needs_review": False, "reason": ""}

        monkeypatch.setattr(
            inline_comment_drift.InlineCommentDrift,
            "_llm_compare",
            staticmethod(mock_compare),
        )

        from tests.mock_provider import MockProvider
        provider = MockProvider(health=True)
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": provider},
        )
        detector.detect(ctx)

        # Both file types should be scanned
        extensions = {f.rsplit(".", 1)[-1] for f in scanned_files}
        assert "py" in extensions
        assert "js" in extensions
