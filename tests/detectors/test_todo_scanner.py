"""Tests for the TODO scanner detector."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sentinel.detectors.todo_scanner import TodoScanner
from sentinel.models import DetectorContext, DetectorTier, Severity, ScopeType


@pytest.fixture
def scanner():
    return TodoScanner()


@pytest.fixture
def repo_with_todos(tmp_path):
    """Create a temporary repo with TODO comments."""
    (tmp_path / "src").mkdir()

    (tmp_path / "src" / "main.py").write_text(
        "# TODO: fix the widget\n"
        "x = 1\n"
        "# FIXME: broken thing\n"
        "y = 2\n"
    )

    (tmp_path / "src" / "utils.py").write_text(
        "# HACK: temporary workaround\n"
        "def hack():\n"
        "    pass\n"
    )

    (tmp_path / "clean.py").write_text(
        "# This file is clean\n"
        "z = 3\n"
    )

    return tmp_path


@pytest.fixture
def repo_empty(tmp_path):
    """An empty repo directory."""
    return tmp_path


class TestTodoScanner:
    def test_properties(self, scanner):
        assert scanner.name == "todo-scanner"
        assert scanner.tier == DetectorTier.DETERMINISTIC
        assert "todo-fixme" in scanner.categories

    def test_finds_todos(self, scanner, repo_with_todos):
        ctx = DetectorContext(repo_root=str(repo_with_todos))
        findings = scanner.detect(ctx)
        assert len(findings) == 3  # TODO, FIXME, HACK

        tags = {f.context["tag"] for f in findings}
        assert tags == {"TODO", "FIXME", "HACK"}

    def test_severity_mapping(self, scanner, repo_with_todos):
        ctx = DetectorContext(repo_root=str(repo_with_todos))
        findings = scanner.detect(ctx)

        severity_by_tag = {f.context["tag"]: f.severity for f in findings}
        assert severity_by_tag["TODO"] == Severity.LOW
        assert severity_by_tag["FIXME"] == Severity.MEDIUM
        assert severity_by_tag["HACK"] == Severity.HIGH

    def test_empty_repo(self, scanner, repo_empty):
        ctx = DetectorContext(repo_root=str(repo_empty))
        findings = scanner.detect(ctx)
        assert findings == []

    def test_evidence_includes_code(self, scanner, repo_with_todos):
        ctx = DetectorContext(repo_root=str(repo_with_todos))
        findings = scanner.detect(ctx)
        for f in findings:
            assert len(f.evidence) >= 1
            assert f.evidence[0].type.value == "code"
            assert f.evidence[0].content  # Not empty

    def test_incremental_scope(self, scanner, repo_with_todos):
        ctx = DetectorContext(
            repo_root=str(repo_with_todos),
            scope=ScopeType.INCREMENTAL,
            changed_files=["src/main.py"],
        )
        findings = scanner.detect(ctx)
        # Only src/main.py has TODO and FIXME
        assert len(findings) == 2

    def test_targeted_scope(self, scanner, repo_with_todos):
        ctx = DetectorContext(
            repo_root=str(repo_with_todos),
            scope=ScopeType.TARGETED,
            target_paths=["src/utils.py"],
        )
        findings = scanner.detect(ctx)
        assert len(findings) == 1
        assert findings[0].context["tag"] == "HACK"

    def test_skips_binary_extensions(self, scanner, tmp_path):
        (tmp_path / "image.png").write_bytes(b"# TODO: not a real image")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert findings == []

    def test_skips_venv_dirs(self, scanner, tmp_path):
        venv_dir = tmp_path / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "module.py").write_text("# TODO: in venv\n")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert findings == []

    def test_false_positive_prose(self, scanner, tmp_path):
        """'to do' in prose should NOT match — only TODO as a tag."""
        (tmp_path / "readme.md").write_text(
            "There are things to do in this project.\n"
            "We have a list of things we need to do.\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert findings == []

    def test_case_insensitive(self, scanner, tmp_path):
        (tmp_path / "case.py").write_text("# todo: lowercase\n# Todo: mixed\n")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert len(findings) == 2

    def test_finding_fields(self, scanner, repo_with_todos):
        ctx = DetectorContext(repo_root=str(repo_with_todos))
        findings = scanner.detect(ctx)
        for f in findings:
            assert f.detector == "todo-scanner"
            assert f.category == "todo-fixme"
            assert 0.0 <= f.confidence <= 1.0
            assert f.file_path is not None
            assert f.line_start is not None
