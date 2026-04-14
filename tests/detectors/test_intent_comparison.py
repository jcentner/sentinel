"""Tests for the intent-comparison detector (multi-artifact triangulation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from sentinel.core.extractors import has_tree_sitter
from sentinel.detectors.intent_comparison import (
    IntentComparisonDetector,
    _build_doc_lookup,
    _build_evidence,
    _build_test_lookup,
    _extract_symbols,
    _filter_contradictions,
    _find_tests_for_symbol,
    _gather_artifacts,
    _llm_triangulate,
    _parse_sections,
    _sort_by_risk,
)
from sentinel.models import (
    CapabilityTier,
    DetectorContext,
    DetectorTier,
    ScopeType,
)

_skip_no_tree_sitter = pytest.mark.skipif(
    not has_tree_sitter(), reason="tree-sitter not installed",
)

# ── Detector metadata ──────────────────────────────────────────────


class TestDetectorMeta:
    def test_name(self) -> None:
        d = IntentComparisonDetector()
        assert d.name == "intent-comparison"

    def test_tier(self) -> None:
        d = IntentComparisonDetector()
        assert d.tier == DetectorTier.LLM_ASSISTED

    def test_capability_tier(self) -> None:
        d = IntentComparisonDetector()
        assert d.capability_tier == CapabilityTier.ADVANCED

    def test_categories(self) -> None:
        d = IntentComparisonDetector()
        assert d.categories == ["cross-artifact"]

    def test_description_not_empty(self) -> None:
        d = IntentComparisonDetector()
        assert len(d.description) > 10

    def test_not_enabled_by_default(self) -> None:
        d = IntentComparisonDetector()
        assert d.enabled_by_default is False


# ── Symbol extraction ──────────────────────────────────────────────


class TestExtractSymbols:
    def test_function_with_docstring(self) -> None:
        source = '''
def greet(name: str) -> str:
    """Return a personalized greeting message for the given user.

    Args:
        name: The user's display name to greet.
    """
    prefix = "Hello"
    msg = f"{prefix}, {name}"
    suffix = "!"
    return msg + suffix
'''
        result = _extract_symbols(source)
        assert len(result) == 1
        assert result[0]["name"] == "greet"
        assert "docstring" in result[0]
        assert "code" in result[0]
        assert result[0]["line_start"] == 2

    def test_function_without_docstring(self) -> None:
        source = '''
def helper(x):
    a = x + 1
    b = a * 2
    c = b - 1
    return c
'''
        result = _extract_symbols(source)
        assert len(result) == 1
        assert "docstring" not in result[0]

    def test_class_with_docstring(self) -> None:
        source = '''
class Widget:
    """A reusable UI widget component for the dashboard interface.

    Supports configuration, rendering, and event handling.
    """
    def __init__(self):
        self.active = True
        self.visible = True
        self.enabled = True
'''
        result = _extract_symbols(source)
        # Class and __init__ may both appear
        names = [s["name"] for s in result]
        assert "Widget" in names

    def test_skips_trivial_functions(self) -> None:
        source = '''
def trivial():
    """A trivially short function with no real body."""
    pass
'''
        result = _extract_symbols(source)
        # Only has `pass` — less than _MIN_CODE_LINES lines
        assert len(result) == 0

    def test_skips_short_docstrings(self) -> None:
        source = '''
def process(data):
    """Process data."""
    result = []
    for item in data:
        result.append(item * 2)
    return result
'''
        result = _extract_symbols(source)
        assert len(result) == 1
        # "Process data." is < 30 chars → no docstring in symbol
        assert "docstring" not in result[0]

    def test_syntax_error_returns_empty(self) -> None:
        result = _extract_symbols("def broken(:\n    pass")
        assert result == []

    def test_async_function(self) -> None:
        source = '''
async def fetch_data(url: str) -> dict:
    """Fetch data from a remote HTTP endpoint asynchronously.

    Returns parsed JSON response body.
    """
    response = await client.get(url)
    data = response.json()
    validated = validate(data)
    return validated
'''
        result = _extract_symbols(source)
        assert len(result) == 1
        assert result[0]["name"] == "fetch_data"
        assert "docstring" in result[0]


# ── Test lookup ────────────────────────────────────────────────────


class TestBuildTestLookup:
    def test_finds_test_functions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_foo.py"
        test_file.write_text(
            "def test_bar():\n"
            "    result = bar()\n"
            "    assert result == 42\n"
            "    assert isinstance(result, int)\n",
        )
        lookup = _build_test_lookup(tmp_path)
        assert "bar" in lookup
        assert "test_bar" in lookup["bar"]

    def test_skips_non_test_files(self, tmp_path: Path) -> None:
        (tmp_path / "helper.py").write_text(
            "def test_something():\n    pass\n    pass\n    pass\n"
        )
        lookup = _build_test_lookup(tmp_path)
        assert len(lookup) == 0

    def test_skips_short_tests(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_short.py"
        test_file.write_text("def test_x():\n    pass\n")
        lookup = _build_test_lookup(tmp_path)
        assert len(lookup) == 0

    def test_skips_common_dirs(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "test_foo.py"
        venv.parent.mkdir()
        venv.write_text(
            "def test_bar():\n"
            "    result = bar()\n"
            "    assert result == 42\n"
            "    assert isinstance(result, int)\n",
        )
        lookup = _build_test_lookup(tmp_path)
        assert len(lookup) == 0


class TestFindTestsForSymbol:
    def test_exact_match(self) -> None:
        lookup = {"run_scan": {"test_run_scan": "body"}}
        result = _find_tests_for_symbol("run_scan", lookup)
        assert "test_run_scan" in result

    def test_prefix_match(self) -> None:
        lookup = {"run_scan_full": {"test_run_scan_full": "body"}}
        result = _find_tests_for_symbol("run_scan", lookup)
        assert "test_run_scan_full" in result

    def test_no_match(self) -> None:
        lookup = {"unrelated": {"test_unrelated": "body"}}
        result = _find_tests_for_symbol("run_scan", lookup)
        assert len(result) == 0


# ── Doc lookup ─────────────────────────────────────────────────────


class TestParseMonkeySection:
    def test_basic_sections(self) -> None:
        content = (
            "# Heading One\n"
            "\n"
            "Body of heading one with enough content to pass the minimum "
            "section length threshold for analysis.\n"
            "\n"
            "## Heading Two\n"
            "\n"
            "Body of heading two also with enough meaningful content to "
            "pass the minimum threshold for section analysis.\n"
        )
        sections = _parse_sections(content)
        assert len(sections) == 2
        assert sections[0]["title"] == "Heading One"
        assert sections[1]["title"] == "Heading Two"

    def test_skips_short_sections(self) -> None:
        content = "# Short\n\nToo brief.\n"
        sections = _parse_sections(content)
        assert len(sections) == 0


class TestBuildDocLookup:
    def test_finds_symbol_refs(self, tmp_path: Path) -> None:
        doc = tmp_path / "README.md"
        doc.write_text(
            "# API Reference\n"
            "\n"
            "The `run_scan()` function is the main entry point for scanning "
            "repositories for issues. It accepts a config object and returns "
            "a list of findings.\n"
        )
        lookup = _build_doc_lookup(tmp_path)
        assert "run_scan" in lookup
        assert lookup["run_scan"][0]["file"] == "README.md"

    def test_ignores_nonexistent_symbols(self, tmp_path: Path) -> None:
        doc = tmp_path / "guide.md"
        doc.write_text("# Setup\n\nJust run the install command to get started with the basic configuration.\n")
        lookup = _build_doc_lookup(tmp_path)
        # No backtick symbols → empty
        assert len(lookup) == 0


# ── Artifact gathering ─────────────────────────────────────────────


class TestGatherArtifacts:
    def test_code_only(self, tmp_path: Path) -> None:
        sym = {
            "name": "process",
            "code": "result = []\nfor x in data:\n    result.append(x)\nreturn result",
            "line_start": 1,
            "code_start": 1,
            "code_end": 4,
        }
        artifacts = _gather_artifacts(
            sym, tmp_path / "mod.py", "mod.py", tmp_path, {}, {},
        )
        assert "code" in artifacts
        assert "docstring" not in artifacts
        assert "tests" not in artifacts
        assert "doc_sections" not in artifacts

    def test_all_four_artifacts(self, tmp_path: Path) -> None:
        sym = {
            "name": "run_scan",
            "code": "findings = []\nfor d in detectors:\n    findings.extend(d.detect())\nreturn findings",
            "docstring": "Execute a full repository scan using all enabled detectors and return findings list.",
            "line_start": 10,
            "code_start": 14,
            "code_end": 20,
            "docstring_end": 13,
        }
        test_lookup: dict[str, dict[str, str]] = {
            "run_scan": {
                "test_run_scan": "def test_run_scan():\n    ...\n    assert len(r) > 0\n    assert r == expected",
            },
        }
        doc_lookup: dict[str, list[dict[str, Any]]] = {
            "run_scan": [{
                "title": "API",
                "body": "`run_scan()` returns findings for all configured detectors. It accepts a config object.",
                "file": "docs/api.md",
                "line_start": 5,
            }],
        }
        artifacts = _gather_artifacts(
            sym, tmp_path / "runner.py", "runner.py", tmp_path,
            test_lookup, doc_lookup,
        )
        assert "code" in artifacts
        assert "docstring" in artifacts
        assert "tests" in artifacts
        assert "doc_sections" in artifacts
        assert len(artifacts) == 4

    def test_limits_tests_to_three(self, tmp_path: Path) -> None:
        sym = {
            "name": "process",
            "code": "a = 1\nb = 2\nc = 3\nreturn a + b + c",
            "docstring": "Process the input and return a computed result with all values combined.",
            "line_start": 1,
            "code_start": 3,
            "code_end": 6,
        }
        test_lookup: dict[str, dict[str, str]] = {
            "process": {
                f"test_process_{i}": f"body_{i}\n...\n...\n..."
                for i in range(5)
            },
        }
        artifacts = _gather_artifacts(
            sym, tmp_path / "mod.py", "mod.py", tmp_path,
            test_lookup, {},
        )
        assert len(artifacts["tests"]) == 3


# ── LLM triangulation ─────────────────────────────────────────────


class TestLLMTriangulate:
    def _make_provider(self, response_text: str) -> MagicMock:
        provider = MagicMock()
        provider.model = "test-model"
        resp = MagicMock()
        resp.text = response_text
        resp.token_count = 42
        resp.duration_ms = 100.0
        provider.generate.return_value = resp
        return provider

    def test_no_contradictions(self) -> None:
        provider = self._make_provider(
            json.dumps({"contradictions": []}),
        )
        result = _llm_triangulate(
            sym_name="foo",
            artifacts={
                "code": "return 1",
                "docstring": "Returns one.",
                "tests": [{"test_name": "test_foo", "test_body": "assert foo() == 1"}],
            },
            file_path="mod.py",
            line_start=1,
            provider=provider,
        )
        assert result is not None
        assert result["contradictions"] == []

    def test_contradiction_found(self) -> None:
        provider = self._make_provider(
            json.dumps({
                "contradictions": [
                    {
                        "between": ["docstring", "code"],
                        "reason": "Docstring claims function returns a list of results, but code actually returns integer 42",
                        "quote_a": "Returns a list of results from the computation pipeline.",
                        "quote_b": "return 42",
                    }
                ],
            }),
        )
        result = _llm_triangulate(
            sym_name="compute",
            artifacts={
                "code": "return 42",
                "docstring": "Returns a list of results from the computation pipeline.",
                "tests": [{"test_name": "test_compute", "test_body": "assert compute() == [1]"}],
            },
            file_path="calc.py",
            line_start=5,
            provider=provider,
        )
        assert result is not None
        assert len(result["contradictions"]) == 1
        assert result["contradictions"][0]["between"] == ["docstring", "code"]

    def test_malformed_json_returns_none(self) -> None:
        provider = self._make_provider("not json at all")
        result = _llm_triangulate(
            sym_name="foo",
            artifacts={"code": "pass", "docstring": "x", "tests": []},
            file_path="mod.py",
            line_start=1,
            provider=provider,
        )
        assert result is None

    def test_invalid_structure_returns_none(self) -> None:
        """Response is valid JSON but contradictions is not a list."""
        provider = self._make_provider(
            json.dumps({"contradictions": "not a list"}),
        )
        result = _llm_triangulate(
            sym_name="foo",
            artifacts={"code": "pass", "docstring": "x", "tests": []},
            file_path="mod.py",
            line_start=1,
            provider=provider,
        )
        assert result is None

    def test_llm_exception_returns_none(self) -> None:
        provider = MagicMock()
        provider.model = "test-model"
        provider.generate.side_effect = RuntimeError("connection failed")
        result = _llm_triangulate(
            sym_name="foo",
            artifacts={"code": "pass", "docstring": "x", "tests": []},
            file_path="mod.py",
            line_start=1,
            provider=provider,
        )
        assert result is None

    def test_enhanced_mode_sets_severity(self) -> None:
        provider = self._make_provider(
            json.dumps({
                "contradictions": [
                    {
                        "between": ["test", "docstring"],
                        "severity": "high",
                        "reason": "Test verifies return value is a dict, but docstring claims it returns a list of data entries",
                        "quote_a": "assert isinstance(get_data(), dict)",
                        "quote_b": "Returns a list of all data entries retrieved from storage.",
                    }
                ],
            }),
        )
        result = _llm_triangulate(
            sym_name="get_data",
            artifacts={
                "code": "return {}",
                "docstring": "Returns a list of all data entries retrieved from storage.",
                "tests": [{"test_name": "test_get_data", "test_body": "assert isinstance(get_data(), dict)"}],
            },
            file_path="data.py",
            line_start=1,
            provider=provider,
            use_enhanced=True,
        )
        assert result is not None
        assert result["contradictions"][0]["severity"] == "high"

    def test_logs_to_db(self, tmp_path: Path) -> None:
        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE llm_log ("
            "  id INTEGER PRIMARY KEY,"
            "  run_id INTEGER,"
            "  timestamp TEXT,"
            "  purpose TEXT,"
            "  model TEXT,"
            "  detector TEXT,"
            "  finding_fingerprint TEXT,"
            "  finding_title TEXT,"
            "  prompt TEXT,"
            "  response TEXT,"
            "  tokens_generated INTEGER,"
            "  generation_ms REAL,"
            "  verdict TEXT,"
            "  is_real INTEGER,"
            "  adjusted_severity TEXT,"
            "  summary TEXT"
            ")"
        )

        provider = self._make_provider(
            json.dumps({"contradictions": []}),
        )
        _llm_triangulate(
            sym_name="bar",
            artifacts={
                "code": "return 1",
                "docstring": "Returns one from the computation pipeline.",
                "tests": [{"test_name": "test_bar", "test_body": "assert bar() == 1"}],
            },
            file_path="m.py",
            line_start=1,
            provider=provider,
            conn=conn,
            run_id=1,
        )

        rows = conn.execute("SELECT purpose, verdict FROM llm_log").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "intent-comparison"
        assert rows[0][1] == "no_contradiction"
        conn.close()

    def test_logs_contradiction_verdict(self, tmp_path: Path) -> None:
        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE llm_log ("
            "  id INTEGER PRIMARY KEY,"
            "  run_id INTEGER,"
            "  timestamp TEXT,"
            "  purpose TEXT,"
            "  model TEXT,"
            "  detector TEXT,"
            "  finding_fingerprint TEXT,"
            "  finding_title TEXT,"
            "  prompt TEXT,"
            "  response TEXT,"
            "  tokens_generated INTEGER,"
            "  generation_ms REAL,"
            "  verdict TEXT,"
            "  is_real INTEGER,"
            "  adjusted_severity TEXT,"
            "  summary TEXT"
            ")"
        )

        provider = self._make_provider(
            json.dumps({
                "contradictions": [
                    {"between": ["code", "docstring"], "reason": "Code returns an empty list but docstring claims it returns an integer count of items in the collection", "quote_a": "return []", "quote_b": "Returns an integer count of items in the collection."},
                ],
            }),
        )
        _llm_triangulate(
            sym_name="baz",
            artifacts={
                "code": "return []",
                "docstring": "Returns an integer count of items in the collection.",
                "tests": [{"test_name": "test_baz", "test_body": "assert baz() == 0"}],
            },
            file_path="m.py",
            line_start=1,
            provider=provider,
            conn=conn,
            run_id=2,
        )

        rows = conn.execute("SELECT verdict, summary FROM llm_log").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "contradiction_found"
        assert "returns" in rows[0][1].lower()
        conn.close()


# ── Evidence builder ───────────────────────────────────────────────


class TestBuildEvidence:
    def _sym(self) -> dict[str, Any]:
        return {
            "name": "foo",
            "code": "return 42",
            "line_start": 1,
            "code_start": 3,
            "code_end": 5,
            "docstring": "Returns the answer.",
            "docstring_end": 2,
        }

    def test_code_always_included(self) -> None:
        evidence = _build_evidence(
            self._sym(),
            {"code": "return 42"},
            [],
            "mod.py",
        )
        assert len(evidence) == 1
        assert evidence[0].type.value == "code"

    def test_docstring_pair(self) -> None:
        evidence = _build_evidence(
            self._sym(),
            {"code": "return 42", "docstring": "Returns the answer."},
            ["code", "docstring"],
            "mod.py",
        )
        types = [e.type.value for e in evidence]
        assert "code" in types
        assert "doc" in types
        assert len(evidence) == 2

    def test_test_pair(self) -> None:
        evidence = _build_evidence(
            self._sym(),
            {
                "code": "return 42",
                "tests": [{"test_name": "test_foo", "test_body": "assert foo() == 42"}],
            },
            ["code", "test"],
            "mod.py",
        )
        types = [e.type.value for e in evidence]
        assert "test" in types

    def test_documentation_pair(self) -> None:
        evidence = _build_evidence(
            self._sym(),
            {
                "code": "return 42",
                "doc_sections": [{"title": "API", "body": "foo returns 42", "file": "api.md", "line_start": 5}],
            },
            ["code", "documentation"],
            "mod.py",
        )
        types = [e.type.value for e in evidence]
        assert "doc" in types

    def test_both_sides_of_non_code_pair(self) -> None:
        """Contradiction between docstring and test should include both."""
        evidence = _build_evidence(
            self._sym(),
            {
                "code": "return 42",
                "docstring": "Returns list.",
                "tests": [{"test_name": "test_foo", "test_body": "assert foo() == 42"}],
            },
            ["docstring", "test"],
            "mod.py",
        )
        types = [e.type.value for e in evidence]
        assert "code" in types  # always present
        assert "doc" in types  # docstring
        assert "test" in types  # test
        assert len(evidence) == 3

    def test_unrecognized_pair_names(self) -> None:
        """Unknown artifact names only produce code evidence."""
        evidence = _build_evidence(
            self._sym(),
            {"code": "return 42"},
            ["unknown1", "unknown2"],
            "mod.py",
        )
        assert len(evidence) == 1
        assert evidence[0].type.value == "code"


# ── Post-LLM filtering ─────────────────────────────────────────────


class TestFilterContradictions:
    """Tests for the post-LLM filtering that removes likely false positives."""

    VALID_NAMES = ["code", "docstring", "test", "documentation"]

    def test_accepts_valid_contradiction_with_quotes(self) -> None:
        result = _filter_contradictions(
            [
                {
                    "between": ["code", "docstring"],
                    "reason": "Code returns an integer but docstring claims it returns a list of results",
                    "quote_a": "return 42",
                    "quote_b": "Returns a list of results from the pipeline.",
                },
            ],
            self.VALID_NAMES,
        )
        assert len(result) == 1

    def test_rejects_short_reason(self) -> None:
        result = _filter_contradictions(
            [{"between": ["code", "test"], "reason": "mismatch"}],
            self.VALID_NAMES,
        )
        assert len(result) == 0

    def test_rejects_vague_language(self) -> None:
        result = _filter_contradictions(
            [
                {
                    "between": ["code", "docstring"],
                    "reason": "The docstring seems to describe something potentially different from the code",
                    "quote_a": "return 42",
                    "quote_b": "Returns a value",
                },
            ],
            self.VALID_NAMES,
        )
        assert len(result) == 0

    def test_rejects_invalid_artifact_pair(self) -> None:
        result = _filter_contradictions(
            [
                {
                    "between": ["unknown_artifact", "code"],
                    "reason": "Some long enough reason text that passes the length check easily here.",
                    "quote_a": "quote one",
                    "quote_b": "quote two",
                },
            ],
            self.VALID_NAMES,
        )
        assert len(result) == 0

    def test_rejects_missing_pair(self) -> None:
        result = _filter_contradictions(
            [{"reason": "Long reason that should pass the length check here."}],
            self.VALID_NAMES,
        )
        assert len(result) == 0

    def test_accepts_long_reason_without_quotes(self) -> None:
        result = _filter_contradictions(
            [
                {
                    "between": ["code", "documentation"],
                    "reason": (
                        "The documentation states that the function returns a tuple of "
                        "valid records and errors, but the code actually returns a dictionary "
                        "with keys 'results', 'errors', and 'total'"
                    ),
                },
            ],
            self.VALID_NAMES,
        )
        assert len(result) == 1

    def test_rejects_short_reason_without_quotes(self) -> None:
        result = _filter_contradictions(
            [
                {
                    "between": ["code", "documentation"],
                    "reason": "Documentation says returns tuple, code returns dict",
                },
            ],
            self.VALID_NAMES,
        )
        assert len(result) == 0

    def test_filters_mixed_valid_and_invalid(self) -> None:
        result = _filter_contradictions(
            [
                {
                    "between": ["code", "docstring"],
                    "reason": "Code returns an integer 42 but docstring claims it returns a list of results from computation",
                    "quote_a": "return 42",
                    "quote_b": "Returns a list of results.",
                },
                {"between": ["code", "test"], "reason": "short"},
                {
                    "between": ["code", "test"],
                    "reason": "The test seems to possibly check something different from what the code does",
                    "quote_a": "return 42",
                    "quote_b": "assert result == []",
                },
            ],
            self.VALID_NAMES,
        )
        assert len(result) == 1


# ── Full detector integration ──────────────────────────────────────


class TestIntentComparisonDetector:
    def _make_provider(self, response_text: str) -> MagicMock:
        provider = MagicMock()
        provider.model = "test-model"
        provider.check_health.return_value = True
        resp = MagicMock()
        resp.text = response_text
        resp.token_count = 42
        resp.duration_ms = 100.0
        provider.generate.return_value = resp
        return provider

    def test_skip_llm_returns_empty(self, tmp_path: Path) -> None:
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"skip_llm": True},
        )
        assert d.detect(ctx) == []

    def test_no_provider_returns_empty(self, tmp_path: Path) -> None:
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={},
        )
        assert d.detect(ctx) == []

    def test_unhealthy_provider_returns_empty(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.check_health.return_value = False
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
        )
        assert d.detect(ctx) == []

    def test_no_python_files_returns_empty(self, tmp_path: Path) -> None:
        provider = self._make_provider('{"contradictions": []}')
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
        )
        assert d.detect(ctx) == []

    def test_needs_three_artifacts_minimum(self, tmp_path: Path) -> None:
        """Function with only code + docstring (2 artifacts) should be skipped."""
        (tmp_path / "mod.py").write_text(
            'def greet(name):\n'
            '    """Return a personalized greeting message for the given user name.\n\n'
            '    Args:\n'
            '        name: The display name to use in the greeting.\n'
            '    """\n'
            '    prefix = "Hello"\n'
            '    suffix = "!"\n'
            '    return f"{prefix}, {name}{suffix}"\n'
        )
        provider = self._make_provider('{"contradictions": []}')
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
        )
        result = d.detect(ctx)
        # Only 2 artifacts (code + docstring) → no LLM call
        provider.generate.assert_not_called()
        assert result == []

    def test_triangulates_with_three_artifacts(self, tmp_path: Path) -> None:
        """Function with code + docstring + test (3 artifacts) triggers LLM."""
        (tmp_path / "mod.py").write_text(
            'def compute(x):\n'
            '    """Multiply the input by two and return the doubled value.\n\n'
            '    Args:\n'
            '        x: The numeric value to double.\n'
            '    """\n'
            '    result = x * 2\n'
            '    processed = result + 0\n'
            '    validated = processed\n'
            '    return validated\n'
        )
        (tmp_path / "test_mod.py").write_text(
            "def test_compute():\n"
            "    result = compute(5)\n"
            "    assert result == 10\n"
            "    assert isinstance(result, int)\n"
        )
        provider = self._make_provider(
            json.dumps({
                "contradictions": [
                    {
                        "between": ["docstring", "test"],
                        "reason": "Docstring says multiply input by two, but test expects result of 10 for input 5 which confirms multiplication behavior",
                        "quote_a": "Multiply the input by two and return the doubled value.",
                        "quote_b": "assert result == 10",
                    }
                ],
            }),
        )
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
        )
        result = d.detect(ctx)
        assert len(result) == 1
        assert result[0].detector == "intent-comparison"
        assert result[0].category == "cross-artifact"
        assert "compute" in result[0].title
        assert result[0].context["artifact_count"] == 3

    def test_four_artifacts_with_doc(self, tmp_path: Path) -> None:
        """All four artifact types present."""
        (tmp_path / "mod.py").write_text(
            'def run_scan(config):\n'
            '    """Execute a full repository scan with all enabled detectors.\n\n'
            '    Returns a list of Finding objects identified during the scan.\n'
            '    """\n'
            '    findings = []\n'
            '    for d in config.detectors:\n'
            '        results = d.detect()\n'
            '        findings.extend(results)\n'
            '    return findings\n'
        )
        (tmp_path / "test_mod.py").write_text(
            "def test_run_scan():\n"
            "    result = run_scan(config)\n"
            "    assert len(result) > 0\n"
            "    assert isinstance(result, list)\n"
        )
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "api.md").write_text(
            "# API Reference\n\n"
            "The `run_scan()` function is the main entry point for running "
            "a repository scan. It returns a dictionary of results grouped "
            "by detector name rather than a flat list of findings.\n"
        )
        provider = self._make_provider(
            json.dumps({
                "contradictions": [
                    {
                        "between": ["documentation", "code"],
                        "reason": "Documentation says function returns a dictionary of results grouped by detector name, but code returns a flat list of findings",
                        "quote_a": "It returns a dictionary of results grouped by detector name",
                        "quote_b": "findings = [] ... return findings",
                    }
                ],
            }),
        )
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
        )
        result = d.detect(ctx)
        assert len(result) == 1
        assert result[0].context["artifact_count"] == 4

    def test_no_contradictions_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'def add(a, b):\n'
            '    """Add two numbers together and return their numeric sum.\n\n'
            '    Args:\n'
            '        a: First number.\n'
            '        b: Second number.\n'
            '    """\n'
            '    result = a + b\n'
            '    validated = result\n'
            '    final = validated\n'
            '    return final\n'
        )
        (tmp_path / "test_mod.py").write_text(
            "def test_add():\n"
            "    result = add(1, 2)\n"
            "    assert result == 3\n"
            "    assert isinstance(result, int)\n"
        )
        provider = self._make_provider(
            json.dumps({"contradictions": []}),
        )
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
        )
        result = d.detect(ctx)
        assert result == []

    def test_targeted_scope(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text(
            'def foo():\n'
            '    """Return the default foo value for initialization purposes.\n\n'
            '    Used during startup to set the initial state.\n'
            '    """\n'
            '    val = 42\n'
            '    result = val\n'
            '    checked = result\n'
            '    return checked\n'
        )
        (tmp_path / "test_mod.py").write_text(
            "def test_foo():\n"
            "    result = foo()\n"
            "    assert result == 42\n"
            "    assert result > 0\n"
        )
        provider = self._make_provider(
            json.dumps({"contradictions": []}),
        )
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.TARGETED,
            target_paths=["mod.py"],
            config={"provider": provider},
        )
        d.detect(ctx)
        # Should have scanned mod.py (targeted)
        assert provider.generate.called

    def test_exception_in_detect_returns_empty(self, tmp_path: Path) -> None:
        """detect() catches exceptions and returns empty."""
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root="/nonexistent/path/that/will/cause/error",
            scope=ScopeType.FULL,
            config={"provider": MagicMock(check_health=lambda: True)},
        )
        # Should not raise
        result = d.detect(ctx)
        assert isinstance(result, list)

    def test_skips_test_files_as_targets(self, tmp_path: Path) -> None:
        """Test files themselves should not be analyzed for symbols."""
        (tmp_path / "test_foo.py").write_text(
            'def test_something():\n'
            '    """Verify that the something function works as expected correctly.\n\n'
            '    This test checks the basic functionality.\n'
            '    """\n'
            '    result = something()\n'
            '    assert result is not None\n'
            '    assert result == expected\n'
        )
        # Another test file as "tests"
        (tmp_path / "test_test_foo.py").write_text(
            "def test_test_something():\n"
            "    pass\n    pass\n    pass\n"
        )
        provider = self._make_provider('{"contradictions": []}')
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
        )
        d.detect(ctx)
        provider.generate.assert_not_called()

    def test_risk_signals_sorting(self, tmp_path: Path) -> None:
        """Risk signals should sort files for LLM priority."""
        (tmp_path / "hot.py").write_text(
            'def hot_func():\n'
            '    """A function in a hot file with lots of recent churn activity.\n\n'
            '    This function is frequently modified.\n'
            '    """\n'
            '    a = 1\n'
            '    b = 2\n'
            '    c = a + b\n'
            '    return c\n'
        )
        (tmp_path / "cold.py").write_text(
            'def cold_func():\n'
            '    """A function in a cold file with minimal recent changes.\n\n'
            '    This function is rarely modified.\n'
            '    """\n'
            '    x = 10\n'
            '    y = 20\n'
            '    z = x + y\n'
            '    return z\n'
        )
        # Tests for both
        (tmp_path / "test_hot.py").write_text(
            "def test_hot_func():\n"
            "    val = hot_func()\n"
            "    assert val == 3\n"
            "    assert val > 0\n"
        )
        (tmp_path / "test_cold.py").write_text(
            "def test_cold_func():\n"
            "    val = cold_func()\n"
            "    assert val == 30\n"
            "    assert val > 0\n"
        )
        provider = self._make_provider(
            json.dumps({"contradictions": []}),
        )
        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.FULL,
            config={"provider": provider},
            risk_signals={
                "hot.py": {
                    "is_hotspot": True,
                    "churn_commits": 50,
                    "churn_fix_ratio": 0.5,
                    "author_count": 3,
                },
                "cold.py": {
                    "is_hotspot": True,
                    "churn_commits": 2,
                    "churn_fix_ratio": 0.0,
                    "author_count": 1,
                },
            },
        )
        d.detect(ctx)
        # With risk signals, hot.py should be analyzed first
        # (both get analyzed since _MAX_PER_SCAN=50)
        assert provider.generate.called


# ── Risk sorting ───────────────────────────────────────────────────


class TestSortByRisk:
    def test_sorts_high_churn_first(self, tmp_path: Path) -> None:
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.touch()
        b.touch()
        signals = {
            "a.py": {"churn_commits": 5, "churn_fix_ratio": 0.1},
            "b.py": {"churn_commits": 20, "churn_fix_ratio": 0.1},
        }
        result = _sort_by_risk([a, b], tmp_path, signals)
        assert result[0] == b

    def test_fix_ratio_bonus(self, tmp_path: Path) -> None:
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.touch()
        b.touch()
        signals = {
            "a.py": {"churn_commits": 15, "churn_fix_ratio": 0.5},
            "b.py": {"churn_commits": 20, "churn_fix_ratio": 0.1},
        }
        result = _sort_by_risk([a, b], tmp_path, signals)
        # a: 15 + 10.0 bonus = 25.0, b: 20 + 0 = 20.0
        assert result[0] == a

    def test_missing_signals_sorts_last(self, tmp_path: Path) -> None:
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.touch()
        b.touch()
        signals = {"b.py": {"churn_commits": 10, "churn_fix_ratio": 0.1}}
        result = _sort_by_risk([a, b], tmp_path, signals)
        assert result[0] == b


# ── JS/TS multi-language support ──────────────────────────────────


@_skip_no_tree_sitter
class TestExtractSymbolsJS:
    def test_js_function_with_jsdoc(self) -> None:
        source = (
            "/**\n"
            " * Return a personalized greeting message for the given user.\n"
            " * @param {string} name - The user's display name\n"
            " */\n"
            "function greet(name) {\n"
            '    const prefix = "Hello";\n'
            '    const msg = `${prefix}, ${name}`;\n'
            '    const suffix = "!";\n'
            "    return msg + suffix;\n"
            "}\n"
        )
        result = _extract_symbols(source, language="javascript")
        assert len(result) == 1
        assert result[0]["name"] == "greet"
        assert "docstring" in result[0]

    def test_ts_function_with_jsdoc(self) -> None:
        source = (
            "/**\n"
            " * Process records with validation and transformation.\n"
            " * Applies strict schema checks on all input records.\n"
            " */\n"
            "export function processRecords(records: any[]): any {\n"
            "    const results = [];\n"
            "    for (const r of records) {\n"
            "        results.push(r);\n"
            "    }\n"
            "    return results;\n"
            "}\n"
        )
        result = _extract_symbols(source, language="typescript")
        assert len(result) == 1
        assert result[0]["name"] == "processRecords"
        assert "docstring" in result[0]

    def test_js_function_no_jsdoc(self) -> None:
        source = (
            "function helper(x) {\n"
            "    const a = x + 1;\n"
            "    const b = a * 2;\n"
            "    const c = b - 1;\n"
            "    return c;\n"
            "}\n"
        )
        result = _extract_symbols(source, language="javascript")
        assert len(result) == 1
        assert "docstring" not in result[0]


@_skip_no_tree_sitter
class TestBuildTestLookupJS:
    def test_finds_js_test_functions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "utils.test.js"
        test_file.write_text(
            "function test_validate() {\n"
            "    const result = validate('hello');\n"
            "    expect(result).toBe(true);\n"
            "    expect(typeof result).toBe('boolean');\n"
            "}\n"
        )
        lookup = _build_test_lookup(tmp_path)
        assert "validate" in lookup

    def test_finds_ts_test_functions(self, tmp_path: Path) -> None:
        test_file = tmp_path / "core.test.ts"
        test_file.write_text(
            "function test_process() {\n"
            "    const result = process('data');\n"
            "    expect(result).toBeDefined();\n"
            "    expect(typeof result).toBe('string');\n"
            "}\n"
        )
        lookup = _build_test_lookup(tmp_path)
        assert "process" in lookup

    def test_skips_non_test_js_files(self, tmp_path: Path) -> None:
        (tmp_path / "helper.js").write_text(
            "function test_something() {\n"
            "    return true;\n"
            "    return true;\n"
            "    return true;\n"
            "}\n"
        )
        lookup = _build_test_lookup(tmp_path)
        assert len(lookup) == 0


@_skip_no_tree_sitter
class TestIntentComparisonDetectorJS:
    def _make_provider(self, response_text: str) -> MagicMock:
        provider = MagicMock()
        provider.model = "test-model"
        resp = MagicMock()
        resp.text = response_text
        resp.token_count = 42
        resp.duration_ms = 100.0
        provider.generate.return_value = resp
        return provider

    def test_triangulates_js_three_artifacts(
        self, tmp_path: Path,
    ) -> None:
        """JS function with code + JSDoc + test triggers LLM."""
        (tmp_path / "mod.js").write_text(
            "/**\n"
            " * Multiply the input by two and return the doubled value.\n"
            " * @param {number} x - Value to double\n"
            " * @returns {number} The doubled value\n"
            " */\n"
            "function compute(x) {\n"
            "    const result = x * 2;\n"
            "    const processed = result + 0;\n"
            "    const validated = processed;\n"
            "    return validated;\n"
            "}\n"
        )
        (tmp_path / "mod.test.js").write_text(
            "function test_compute() {\n"
            "    const result = compute(5);\n"
            "    expect(result).toBe(10);\n"
            "    expect(typeof result).toBe('number');\n"
            "}\n"
        )

        provider = self._make_provider(json.dumps({
            "contradictions": [{
                "description": "Test drift detected in JS code",
                "confidence": 0.8,
            }],
        }))

        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": provider},
        )
        findings = d.detect(ctx)

        assert provider.generate.called
        cross = [f for f in findings if f.category == "cross-artifact"]
        assert len(cross) >= 1
        assert cross[0].file_path.endswith(".js")

    def test_no_finding_when_consistent_js(
        self, tmp_path: Path,
    ) -> None:
        """Consistent JS code produces no findings."""
        (tmp_path / "mod.js").write_text(
            "/**\n"
            " * Add two numbers together and return the sum total.\n"
            " * @param {number} a - First number\n"
            " * @param {number} b - Second number\n"
            " */\n"
            "function add(a, b) {\n"
            "    const result = a + b;\n"
            "    const validated = result;\n"
            "    const checked = validated;\n"
            "    return checked;\n"
            "}\n"
        )
        (tmp_path / "mod.test.js").write_text(
            "function test_add() {\n"
            "    const result = add(1, 2);\n"
            "    expect(result).toBe(3);\n"
            "    expect(typeof result).toBe('number');\n"
            "}\n"
        )

        provider = self._make_provider(json.dumps({
            "contradictions": [],
        }))

        d = IntentComparisonDetector()
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            config={"provider": provider},
        )
        findings = d.detect(ctx)
        assert len(findings) == 0
