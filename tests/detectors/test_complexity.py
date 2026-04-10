"""Tests for the complexity detector."""

from __future__ import annotations

import ast

import pytest

from sentinel.detectors.complexity import (
    ComplexityDetector,
    _cyclomatic_complexity,
    _function_lines,
)
from sentinel.models import DetectorContext, Severity


@pytest.fixture
def detector():
    return ComplexityDetector()


@pytest.fixture
def repo(tmp_path):
    """Create a test repo with Python files of varying complexity."""
    (tmp_path / "simple.py").write_text(
        "def hello():\n"
        "    return 'world'\n"
    )
    (tmp_path / "complex.py").write_text(
        "def tangled(x, y, z):\n"
        + "".join(f"    if x == {i}:\n        y += {i}\n" for i in range(15))
        + "    return y\n"
    )
    (tmp_path / "long.py").write_text(
        "def very_long_function():\n"
        + "".join(f"    x_{i} = {i}\n" for i in range(60))
        + "    return x_0\n"
    )
    (tmp_path / "clean.py").write_text(
        "def clean():\n"
        "    pass\n"
        "\n"
        "class Foo:\n"
        "    def method(self):\n"
        "        return 42\n"
    )
    return tmp_path


# ── cyclomatic complexity calculation ────────────────────────────────


class TestCyclomaticComplexity:
    def test_simple_function(self):
        tree = ast.parse("def f():\n    return 1\n")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 1

    def test_single_if(self):
        tree = ast.parse("def f(x):\n    if x:\n        return 1\n    return 0\n")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 2

    def test_nested_ifs(self):
        tree = ast.parse(
            "def f(x, y):\n"
            "    if x:\n"
            "        if y:\n"
            "            return 1\n"
            "    return 0\n"
        )
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 3

    def test_for_loop(self):
        tree = ast.parse("def f(xs):\n    for x in xs:\n        pass\n")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 2

    def test_while_loop(self):
        tree = ast.parse("def f():\n    while True:\n        break\n")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 2

    def test_except_handler(self):
        tree = ast.parse(
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        pass\n"
            "    except TypeError:\n"
            "        pass\n"
        )
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 3

    def test_boolean_ops(self):
        tree = ast.parse("def f(a, b, c):\n    if a and b or c:\n        pass\n")
        func = tree.body[0]
        # if=1 + and=1 + or=1 + base=1 = 4
        assert _cyclomatic_complexity(func) == 4

    def test_ternary(self):
        tree = ast.parse("def f(x):\n    return 1 if x else 0\n")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 2

    def test_assert(self):
        tree = ast.parse("def f(x):\n    assert x > 0\n")
        func = tree.body[0]
        assert _cyclomatic_complexity(func) == 2


# ── function lines ───────────────────────────────────────────────────


class TestFunctionLines:
    def test_one_liner(self):
        tree = ast.parse("def f():\n    pass\n")
        func = tree.body[0]
        assert _function_lines(func) == 1

    def test_multi_line(self):
        tree = ast.parse("def f():\n    x = 1\n    y = 2\n    return x + y\n")
        func = tree.body[0]
        assert _function_lines(func) == 3


# ── detector integration ─────────────────────────────────────────────


class TestComplexityDetector:
    def test_properties(self, detector):
        assert detector.name == "complexity"
        assert detector.categories == ["code-quality"]

    def test_no_findings_on_simple_code(self, detector, repo):
        ctx = DetectorContext(repo_root=str(repo))
        findings = detector.detect(ctx)
        # Only complex.py and long.py should flag; simple.py and clean.py should not
        flagged_files = {f.file_path for f in findings}
        assert "simple.py" not in flagged_files
        assert "clean.py" not in flagged_files

    def test_flags_high_complexity(self, detector, repo):
        ctx = DetectorContext(repo_root=str(repo))
        findings = detector.detect(ctx)
        complex_findings = [f for f in findings if f.file_path == "complex.py"]
        assert len(complex_findings) >= 1
        assert "cyclomatic complexity" in complex_findings[0].title

    def test_flags_long_function(self, detector, repo):
        ctx = DetectorContext(repo_root=str(repo))
        findings = detector.detect(ctx)
        long_findings = [f for f in findings if f.file_path == "long.py"]
        assert len(long_findings) >= 1
        assert "lines" in long_findings[0].title

    def test_severity_scaling(self, detector, tmp_path):
        """Very high complexity gets MEDIUM or HIGH severity, not just LOW."""
        # 25 nested ifs → CC ~26, well above 2x threshold
        code = "def mega(x):\n" + "".join(
            f"    if x == {i}:\n        x += {i}\n" for i in range(25)
        ) + "    return x\n"
        (tmp_path / "mega.py").write_text(code)
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) >= 1
        assert findings[0].severity in (Severity.MEDIUM, Severity.HIGH)

    def test_skips_syntax_errors(self, detector, tmp_path):
        (tmp_path / "broken.py").write_text("def f(\n")
        ctx = DetectorContext(repo_root=str(tmp_path))
        # Should not crash
        findings = detector.detect(ctx)
        assert findings == []

    def test_targeted_scan(self, detector, repo):
        ctx = DetectorContext(
            repo_root=str(repo),
            target_paths=["simple.py"],
        )
        findings = detector.detect(ctx)
        assert findings == []

    def test_respects_skip_dirs(self, detector, tmp_path):
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        code = "def f():\n" + "".join(f"    if True:\n        x = {i}\n" for i in range(20)) + "    return 1\n"
        (venv / "module.py").write_text(code)
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert findings == []

    def test_async_functions(self, detector, tmp_path):
        """Async functions are also analyzed."""
        code = "async def handler(request):\n" + "".join(
            f"    if request.path == '/{i}':\n        return {i}\n" for i in range(15)
        ) + "    return 0\n"
        (tmp_path / "async_handlers.py").write_text(code)
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) >= 1
        assert "handler" in findings[0].title

    def test_test_files_get_reduced_severity_and_confidence(self, detector, tmp_path):
        """Complex functions in test files get LOW severity and reduced confidence."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        code = "def test_tangled(x):\n" + "".join(
            f"    if x == {i}:\n        assert {i}\n" for i in range(15)
        ) + "    return True\n"
        (tests_dir / "test_example.py").write_text(code)
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = detector.detect(ctx)
        assert len(findings) >= 1
        assert findings[0].severity == Severity.LOW
        assert findings[0].confidence < 0.95  # Demoted from the normal 0.95
