"""Tests for the TODO scanner detector."""

from __future__ import annotations

import pytest

from sentinel.detectors.todo_scanner import TodoScanner
from sentinel.models import DetectorContext, DetectorTier, ScopeType, Severity


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

    def test_skips_string_literal_todos(self, scanner, tmp_path):
        """TODO inside a Python string literal should NOT be flagged."""
        (tmp_path / "test_data.py").write_text(
            '# TODO: fix this real thing\n'
            'test_input = "# TODO: not a real todo\\n"\n'
            "another = '# FIXME: also not real\\n'\n"
            "x = 1  # HACK: this is a real HACK comment\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)

        # Should find: real TODO (line 1), real HACK (line 4)
        # Should NOT find: string TODO (line 2), string FIXME (line 3)
        assert len(findings) == 2
        tags = {f.context["tag"] for f in findings}
        assert tags == {"TODO", "HACK"}

    def test_triple_quoted_string_not_confused(self, scanner, tmp_path):
        """Regular comments after triple-quoted strings should be found."""
        (tmp_path / "example.py").write_text(
            '"""Module docstring."""\n'
            "# TODO: after docstring\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert len(findings) == 1
        assert findings[0].context["tag"] == "TODO"

    def test_skips_mid_sentence_mentions(self, scanner, tmp_path):
        """TODO mentioned mid-sentence in a comment is not an action item."""
        (tmp_path / "test_check.py").write_text(
            "# Should find TODOs/FIXMEs and lint issues\n"
            "x = 1  # At minimum: TODO, FIXME, HACK\n"
            "# This is fine, it matches TODO patterns\n"
            "# TODO: this IS a real todo\n"
            "# FIXME: so is this\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        # Only the direct TODO: and FIXME: at start of comment should match
        assert len(findings) == 2
        tags = {f.context["tag"] for f in findings}
        assert tags == {"TODO", "FIXME"}

    def test_html_comment_todo_in_markdown(self, scanner, tmp_path):
        """<!-- TODO: ... --> in markdown should be detected."""
        (tmp_path / "notes.md").write_text(
            "# My Notes\n"
            "<!-- TODO: update this section -->\n"
            "Some content here.\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert len(findings) == 1
        assert findings[0].context["tag"] == "TODO"
        assert "update this section" in findings[0].title

    def test_html_comment_fixme_in_markdown(self, scanner, tmp_path):
        """<!-- FIXME: ... --> should also be detected."""
        (tmp_path / "readme.md").write_text(
            "<!-- FIXME: broken link below -->\n"
            "[link](broken.md)\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert len(findings) == 1
        assert findings[0].context["tag"] == "FIXME"
        assert findings[0].severity == Severity.MEDIUM

    def test_html_comment_hack_severity(self, scanner, tmp_path):
        """<!-- HACK: ... --> in markdown should be HIGH severity."""
        (tmp_path / "doc.md").write_text("<!-- HACK: workaround for API bug -->\n")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH

    def test_markdown_prose_todo_not_matched(self, scanner, tmp_path):
        """Prose 'TODO' in markdown without HTML comment should not match."""
        (tmp_path / "doc.md").write_text(
            "# TODO List\n"
            "- TODO: buy groceries\n"
            "This is my TODO tracker.\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert findings == []

    def test_multiple_html_comment_todos(self, scanner, tmp_path):
        """Multiple HTML comment TODOs in one file."""
        (tmp_path / "guide.md").write_text(
            "<!-- TODO: add intro section -->\n"
            "# Guide\n"
            "<!-- FIXME: fix the example code -->\n"
            "<!-- XXX: remove before release -->\n"
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = scanner.detect(ctx)
        assert len(findings) == 3
        tags = {f.context["tag"] for f in findings}
        assert tags == {"TODO", "FIXME", "XXX"}

    def test_html_comment_todo_incremental(self, scanner, tmp_path):
        """Incremental scope should include markdown files."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "setup.md").write_text(
            "<!-- TODO: document install steps -->\n"
        )
        (tmp_path / "docs" / "other.md").write_text(
            "<!-- TODO: should not appear -->\n"
        )
        ctx = DetectorContext(
            repo_root=str(tmp_path),
            scope=ScopeType.INCREMENTAL,
            changed_files=["docs/setup.md"],
        )
        findings = scanner.detect(ctx)
        assert len(findings) == 1
        assert "document install steps" in findings[0].title
