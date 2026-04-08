"""Tests for the test-code coherence detector."""

from __future__ import annotations

from sentinel.detectors.test_coherence import (
    TestCoherenceDetector,
    _impl_name_from_test,
    _match_test_to_impl,
    extract_function_pairs,
    find_implementation_file,
    find_test_files,
)
from sentinel.models import DetectorContext, DetectorTier

# ── Detector properties ──────────────────────────────────────────


class TestDetectorProperties:
    def test_name(self):
        d = TestCoherenceDetector()
        assert d.name == "test-coherence"

    def test_tier(self):
        d = TestCoherenceDetector()
        assert d.tier == DetectorTier.LLM_ASSISTED

    def test_categories(self):
        d = TestCoherenceDetector()
        assert "test-coherence" in d.categories


# ── Test file discovery ──────────────────────────────────────────


class TestFindTestFiles:
    def test_finds_test_files(self, tmp_path):
        (tmp_path / "test_foo.py").write_text("def test_x(): pass\n")
        (tmp_path / "bar_test.py").write_text("def test_y(): pass\n")
        (tmp_path / "helper.py").write_text("def helper(): pass\n")

        found = find_test_files(tmp_path)
        names = [f.name for f in found]
        assert "test_foo.py" in names
        assert "bar_test.py" in names
        assert "helper.py" not in names

    def test_skips_common_dirs(self, tmp_path):
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "test_venv.py").write_text("pass\n")
        (tmp_path / "test_real.py").write_text("pass\n")

        found = find_test_files(tmp_path)
        names = [f.name for f in found]
        assert "test_real.py" in names
        assert "test_venv.py" not in names

    def test_skips_egg_info(self, tmp_path):
        egg = tmp_path / "sentinel.egg-info"
        egg.mkdir()
        (egg / "test_egg.py").write_text("pass\n")
        (tmp_path / "test_real.py").write_text("pass\n")

        found = find_test_files(tmp_path)
        assert all("egg-info" not in str(f) for f in found)

    def test_empty_repo(self, tmp_path):
        assert find_test_files(tmp_path) == []


# ── Implementation name derivation ───────────────────────────────


class TestImplNameFromTest:
    def test_test_prefix(self):
        assert _impl_name_from_test("test_config.py") == "config.py"
        assert _impl_name_from_test("test_foo_bar.py") == "foo_bar.py"

    def test_test_suffix(self):
        assert _impl_name_from_test("config_test.py") == "config.py"

    def test_no_pattern(self):
        assert _impl_name_from_test("conftest.py") is None
        assert _impl_name_from_test("helper.py") is None


# ── Implementation file finding ──────────────────────────────────


class TestFindImplementationFile:
    def test_finds_by_naming_convention(self, tmp_path):
        src = tmp_path / "src" / "sentinel"
        src.mkdir(parents=True)
        impl = src / "config.py"
        impl.write_text("class Config: pass\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_config.py"
        test_file.write_text("from sentinel.config import Config\n")

        result = find_implementation_file(test_file, tmp_path)
        assert result is not None
        assert result.name == "config.py"

    def test_prefers_src_dir(self, tmp_path):
        """When the same file exists in src/ and root, prefer src/."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.py").write_text("def func(): pass\n")
        (tmp_path / "foo.py").write_text("# root-level foo\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_foo.py"
        test_file.write_text("import foo\n")

        result = find_implementation_file(test_file, tmp_path)
        assert result is not None
        assert "src" in str(result)

    def test_fallback_to_import_analysis(self, tmp_path):
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("def do_thing(): pass\n")

        test_file = tmp_path / "test_thing.py"
        test_file.write_text("from mypackage.core import do_thing\ndef test_do_thing(): pass\n")

        result = find_implementation_file(test_file, tmp_path)
        assert result is not None
        assert result.name == "core.py"

    def test_returns_none_when_no_match(self, tmp_path):
        test_file = tmp_path / "test_mystery.py"
        test_file.write_text("def test_something(): pass\n")

        result = find_implementation_file(test_file, tmp_path)
        assert result is None


# ── Function matching ────────────────────────────────────────────


class TestMatchTestToImpl:
    def test_exact_match(self):
        lookup = {"run_scan": ("run_scan", "body")}
        assert _match_test_to_impl("test_run_scan", lookup) == "run_scan"

    def test_prefix_match(self):
        lookup = {"build_index": ("build_index", "body")}
        assert _match_test_to_impl("test_build_index_incremental", lookup) == "build_index"

    def test_no_match(self):
        lookup = {"unrelated": ("unrelated", "body")}
        assert _match_test_to_impl("test_something_else", lookup) is None

    def test_short_name_no_false_prefix_match(self):
        """Short impl names should not prefix-match without underscore boundary.

        'run' should not match 'test_running' — only 'run_scan' should.
        """
        lookup = {"run": ("run", "body")}
        assert _match_test_to_impl("test_running", lookup) is None

    def test_short_name_underscore_boundary_match(self):
        """Short impl names DO match when followed by underscore boundary."""
        lookup = {"run": ("run", "body")}
        assert _match_test_to_impl("test_run_scan", lookup) == "run"

    def test_short_name_exact_match_still_works(self):
        """Short impl names work for exact match."""
        lookup = {"do": ("do", "body")}
        assert _match_test_to_impl("test_do", lookup) == "do"

    def test_underscore_boundary_required_for_prefix(self):
        """Prefix match requires underscore after impl name."""
        lookup = {"run": ("run", "body"), "run_scan": ("run_scan", "body")}
        assert _match_test_to_impl("test_run_scan_success", lookup) == "run_scan"

    def test_non_test_function(self):
        lookup = {"foo": ("foo", "body")}
        assert _match_test_to_impl("helper_foo", lookup) is None


# ── Function pair extraction ─────────────────────────────────────


class TestExtractFunctionPairs:
    def test_basic_pairing(self, tmp_path):
        impl = tmp_path / "calculator.py"
        impl.write_text(
            "def add(a, b):\n"
            "    '''Add two numbers.'''\n"
            "    result = a + b\n"
            "    return result\n"
            "\n"
            "def subtract(a, b):\n"
            "    '''Subtract b from a.'''\n"
            "    result = a - b\n"
            "    return result\n"
        )

        test_file = tmp_path / "test_calculator.py"
        test_file.write_text(
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
            "    assert add(0, 0) == 0\n"
            "    assert add(-1, 1) == 0\n"
            "\n"
            "def test_subtract():\n"
            "    assert subtract(5, 3) == 2\n"
            "    assert subtract(0, 0) == 0\n"
            "    assert subtract(1, 5) == -4\n"
        )

        pairs = extract_function_pairs(test_file, impl)
        assert len(pairs) == 2
        test_names = [p[0] for p in pairs]
        impl_names = [p[2] for p in pairs]
        assert "test_add" in test_names
        assert "test_subtract" in test_names
        assert "add" in impl_names
        assert "subtract" in impl_names

    def test_class_methods_paired(self, tmp_path):
        impl = tmp_path / "widget.py"
        impl.write_text(
            "class Widget:\n"
            "    def render(self):\n"
            "        '''Render the widget.'''\n"
            "        output = self.template()\n"
            "        return output\n"
        )

        test_file = tmp_path / "test_widget.py"
        test_file.write_text(
            "class TestWidget:\n"
            "    def test_render(self):\n"
            "        w = Widget()\n"
            "        result = w.render()\n"
            "        assert result is not None\n"
        )

        pairs = extract_function_pairs(test_file, impl)
        assert len(pairs) == 1
        assert pairs[0][0] == "test_render"
        assert pairs[0][2] == "render"

    def test_skips_short_functions(self, tmp_path):
        impl = tmp_path / "tiny.py"
        impl.write_text("def f(): pass\n")

        test_file = tmp_path / "test_tiny.py"
        test_file.write_text("def test_f(): assert True\n")

        pairs = extract_function_pairs(test_file, impl)
        assert len(pairs) == 0  # both too short

    def test_no_impl_functions(self, tmp_path):
        impl = tmp_path / "empty.py"
        impl.write_text("# No functions\nX = 42\n")

        test_file = tmp_path / "test_empty.py"
        test_file.write_text("def test_x():\n    assert True\n    assert True\n    assert True\n")

        pairs = extract_function_pairs(test_file, impl)
        assert len(pairs) == 0

    def test_syntax_error_file(self, tmp_path):
        impl = tmp_path / "bad.py"
        impl.write_text("def broken( :\n")

        test_file = tmp_path / "test_bad.py"
        test_file.write_text("def test_broken():\n    pass\n    pass\n    pass\n")

        pairs = extract_function_pairs(test_file, impl)
        assert len(pairs) == 0


# ── Detector integration (mock LLM) ──────────────────────────────


class TestDetectorIntegration:
    def _make_repo(self, tmp_path):
        """Create a minimal repo with test + impl files."""
        src = tmp_path / "src" / "mylib"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "core.py").write_text(
            "def process(data):\n"
            "    '''Process input data.'''\n"
            "    cleaned = data.strip()\n"
            "    result = cleaned.upper()\n"
            "    return result\n"
        )

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("")
        (tests / "test_core.py").write_text(
            "from mylib.core import process\n\n"
            "def test_process():\n"
            "    result = process('  hello  ')\n"
            "    assert result == 'HELLO'\n"
            "    assert isinstance(result, str)\n"
        )
        return tmp_path

    def test_skip_llm_returns_empty(self, tmp_path):
        repo = self._make_repo(tmp_path)
        d = TestCoherenceDetector()
        ctx = DetectorContext(repo_root=str(repo), config={"skip_llm": True})
        assert d.detect(ctx) == []

    def test_no_provider_returns_empty(self, tmp_path):
        repo = self._make_repo(tmp_path)
        d = TestCoherenceDetector()
        ctx = DetectorContext(repo_root=str(repo), config={})
        assert d.detect(ctx) == []

    def test_unhealthy_provider_returns_empty(self, tmp_path):
        from tests.mock_provider import MockProvider

        repo = self._make_repo(tmp_path)
        d = TestCoherenceDetector()
        ctx = DetectorContext(
            repo_root=str(repo),
            config={"provider": MockProvider(health=False)},
        )
        assert d.detect(ctx) == []

    def test_produces_finding_on_drift(self, tmp_path, monkeypatch):
        from sentinel.detectors import test_coherence
        from tests.mock_provider import MockProvider

        repo = self._make_repo(tmp_path)
        d = TestCoherenceDetector()

        monkeypatch.setattr(
            test_coherence.TestCoherenceDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": True,
                "reason": "Test only checks type, not behavior after recent signature change",
            }),
        )

        ctx = DetectorContext(
            repo_root=str(repo),
            config={"provider": MockProvider(health=True)},
        )
        findings = d.detect(ctx)
        coherence = [f for f in findings if f.category == "test-coherence"]
        assert len(coherence) >= 1
        assert coherence[0].confidence == 0.6
        assert "test_process" in coherence[0].title
        assert coherence[0].context["pattern"] == "test-code-drift"

    def test_no_finding_when_coherent(self, tmp_path, monkeypatch):
        from sentinel.detectors import test_coherence
        from tests.mock_provider import MockProvider

        repo = self._make_repo(tmp_path)
        d = TestCoherenceDetector()

        monkeypatch.setattr(
            test_coherence.TestCoherenceDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: {
                "needs_review": False,
                "reason": "",
            }),
        )

        ctx = DetectorContext(
            repo_root=str(repo),
            config={"provider": MockProvider(health=True)},
        )
        findings = d.detect(ctx)
        coherence = [f for f in findings if f.category == "test-coherence"]
        assert len(coherence) == 0

    def test_handles_llm_parse_failure(self, tmp_path, monkeypatch):
        from sentinel.detectors import test_coherence
        from tests.mock_provider import MockProvider

        repo = self._make_repo(tmp_path)
        d = TestCoherenceDetector()

        monkeypatch.setattr(
            test_coherence.TestCoherenceDetector,
            "_llm_compare",
            staticmethod(lambda *_args, **_kw: None),
        )

        ctx = DetectorContext(
            repo_root=str(repo),
            config={"provider": MockProvider(health=True)},
        )
        findings = d.detect(ctx)
        assert len(findings) == 0  # gracefully returns nothing


# ── _llm_compare direct tests ───────────────────────────────────


class TestLLMCompare:
    def test_parses_json_response(self):
        from tests.mock_provider import MockProvider

        provider = MockProvider(
            generate_text='{"needs_review": true, "reason": "Test is stale"}'
        )
        result = TestCoherenceDetector._llm_compare(
            test_name="test_foo",
            test_body="def test_foo(): assert True",
            impl_name="foo",
            impl_body="def foo(): return 42",
            test_path="tests/test_foo.py",
            impl_path="src/foo.py",
            provider=provider,
        )
        assert result is not None
        assert result["needs_review"] is True
        assert result["reason"] == "Test is stale"
        assert len(provider.generate_calls) == 1
        prompt = provider.generate_calls[0]["prompt"]
        assert "test_foo" in prompt
        assert "foo" in prompt

    def test_returns_none_on_unparseable_response(self):
        from tests.mock_provider import MockProvider

        provider = MockProvider(generate_text="sorry i can't help")
        result = TestCoherenceDetector._llm_compare(
            test_name="test_foo",
            test_body="def test_foo(): pass",
            impl_name="foo",
            impl_body="def foo(): pass",
            test_path="tests/test_foo.py",
            impl_path="src/foo.py",
            provider=provider,
        )
        assert result is None

    def test_logs_to_db(self):
        from sentinel.store.db import get_connection
        from tests.mock_provider import MockProvider

        conn = get_connection(":memory:")

        provider = MockProvider(
            generate_text='{"needs_review": false, "reason": ""}'
        )
        # Use run_id=None to avoid FK constraint on runs table
        TestCoherenceDetector._llm_compare(
            test_name="test_bar",
            test_body="def test_bar(): assert True",
            impl_name="bar",
            impl_body="def bar(): return 1",
            test_path="tests/test_bar.py",
            impl_path="src/bar.py",
            provider=provider,
            conn=conn,
            run_id=None,
        )
        row = conn.execute(
            "SELECT purpose, verdict FROM llm_log WHERE purpose = 'test-coherence-comparison'"
        ).fetchone()
        assert row is not None
        assert row[0] == "test-coherence-comparison"
        assert row[1] == "coherent"
        conn.close()


# ── Async function support ───────────────────────────────────────


class TestAsyncFunctions:
    def test_async_function_pairing(self, tmp_path):
        """Async functions should be extracted and paired correctly."""
        from sentinel.detectors.test_coherence import extract_function_pairs

        impl = tmp_path / "async_module.py"
        impl.write_text(
            "async def fetch_data(url):\n"
            "    '''Fetch data from URL.'''\n"
            "    response = await client.get(url)\n"
            "    return response.json()\n"
        )

        test_file = tmp_path / "test_async_module.py"
        test_file.write_text(
            "async def test_fetch_data():\n"
            "    result = await fetch_data('http://example.com')\n"
            "    assert result is not None\n"
            "    assert isinstance(result, dict)\n"
        )

        pairs = extract_function_pairs(test_file, impl)
        assert len(pairs) == 1
        assert pairs[0][0] == "test_fetch_data"
        assert pairs[0][2] == "fetch_data"
