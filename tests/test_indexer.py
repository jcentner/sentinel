"""Tests for the embedding indexer module."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from sentinel.core.indexer import (
    _collect_files,
    _should_skip_dir,
    _should_skip_file,
    build_index,
    chunk_file,
)
from sentinel.store.db import get_connection


@pytest.fixture
def db_conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    yield conn
    conn.close()


# ── skip helpers ─────────────────────────────────────────────────────


class TestShouldSkipDir:
    def test_skip_known_dirs(self):
        for d in [".git", "__pycache__", "node_modules", ".venv", "dist"]:
            assert _should_skip_dir(d) is True

    def test_skip_egg_info(self):
        assert _should_skip_dir("sentinel.egg-info") is True
        assert _should_skip_dir("foo.egg-info") is True

    def test_allow_normal_dirs(self):
        assert _should_skip_dir("src") is False
        assert _should_skip_dir("tests") is False
        assert _should_skip_dir("docs") is False


class TestShouldSkipFile:
    def test_skip_binary_extensions(self, tmp_path):
        for ext in [".pyc", ".png", ".zip", ".db"]:
            f = tmp_path / f"file{ext}"
            f.write_bytes(b"data")
            assert _should_skip_file(f) is True

    def test_skip_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        assert _should_skip_file(f) is True

    def test_skip_oversized_file(self, tmp_path):
        f = tmp_path / "large.py"
        f.write_text("x" * 600_000)
        assert _should_skip_file(f) is True

    def test_allow_normal_file(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("print('hello')")
        assert _should_skip_file(f) is False

    def test_skip_dotlock_file(self, tmp_path):
        f = tmp_path / "poetry.lock"
        f.write_text("data")
        assert _should_skip_file(f) is True


# ── collect_files ────────────────────────────────────────────────────


class TestCollectFiles:
    def test_collects_text_files(self, tmp_path):
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.md").write_text("docs")
        files = _collect_files(tmp_path)
        names = [f.name for f in files]
        assert "a.py" in names
        assert "b.md" in names

    def test_skips_git_dir(self, tmp_path):
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_text("gitconfig")
        (tmp_path / "main.py").write_text("code")
        files = _collect_files(tmp_path)
        assert all(".git" not in str(f) for f in files)

    def test_recursive_collection(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "inner.py").write_text("code")
        (tmp_path / "outer.py").write_text("code")
        files = _collect_files(tmp_path)
        names = [f.name for f in files]
        assert "inner.py" in names
        assert "outer.py" in names

    def test_skips_egg_info(self, tmp_path):
        egg = tmp_path / "foo.egg-info"
        egg.mkdir()
        (egg / "PKG-INFO").write_text("info")
        (tmp_path / "main.py").write_text("code")
        files = _collect_files(tmp_path)
        assert all("egg-info" not in str(f) for f in files)


# ── chunk_file ───────────────────────────────────────────────────────


class TestChunkFile:
    def test_empty_content(self):
        assert chunk_file("") == []

    def test_small_file(self):
        content = "line1\nline2\nline3\n"
        chunks = chunk_file(content, chunk_size=50, chunk_overlap=10)
        assert len(chunks) == 1
        assert chunks[0]["start_line"] == 1
        assert chunks[0]["end_line"] == 3

    def test_overlapping_chunks(self):
        lines = "\n".join(f"line{i}" for i in range(100)) + "\n"
        chunks = chunk_file(lines, chunk_size=50, chunk_overlap=10)
        assert len(chunks) >= 2
        # Chunks should overlap
        assert chunks[1]["start_line"] < chunks[0]["end_line"]

    def test_whitespace_only_chunks_skipped(self):
        content = "code\n" + "\n" * 100 + "more code\n"
        chunks = chunk_file(content, chunk_size=50, chunk_overlap=10)
        for c in chunks:
            assert c["content"].strip() != ""


# ── build_index ──────────────────────────────────────────────────────


def _mock_embed(texts: list[str], model: str, url: str = "") -> list[list[float]] | None:
    """Return deterministic fake embeddings."""
    return [[0.1, 0.2, 0.3] for _ in texts]


class TestBuildIndex:
    def test_indexes_files(self, tmp_path, db_conn):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("def f():\n    pass\n")
        (repo / "b.py").write_text("x = 1\n")

        with patch("sentinel.core.indexer.embed_texts", _mock_embed):
            stats = build_index(str(repo), db_conn, "test-model")

        assert stats["files_scanned"] == 2
        assert stats["files_indexed"] == 2
        assert stats["chunks_created"] >= 2

    def test_incremental_skips_unchanged(self, tmp_path, db_conn):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("code\n")

        with patch("sentinel.core.indexer.embed_texts", _mock_embed):
            stats1 = build_index(str(repo), db_conn, "test-model")
            stats2 = build_index(str(repo), db_conn, "test-model")

        assert stats1["files_indexed"] == 1
        assert stats2["files_indexed"] == 0  # no changes

    def test_reindexes_changed_file(self, tmp_path, db_conn):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("v1\n")

        with patch("sentinel.core.indexer.embed_texts", _mock_embed):
            build_index(str(repo), db_conn, "test-model")
            (repo / "a.py").write_text("v2\n")
            stats = build_index(str(repo), db_conn, "test-model")

        assert stats["files_indexed"] == 1

    def test_removes_deleted_files(self, tmp_path, db_conn):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("code\n")
        (repo / "b.py").write_text("code\n")

        with patch("sentinel.core.indexer.embed_texts", _mock_embed):
            build_index(str(repo), db_conn, "test-model")
            (repo / "b.py").unlink()
            stats = build_index(str(repo), db_conn, "test-model")

        assert stats["files_removed"] == 1

    def test_embedding_failure_skips_file(self, tmp_path, db_conn):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("code\n")

        def fail_embed(*args: Any, **kwargs: Any) -> None:
            return None

        with patch("sentinel.core.indexer.embed_texts", fail_embed):
            stats = build_index(str(repo), db_conn, "test-model")

        assert stats["files_skipped"] == 1
        assert stats["files_indexed"] == 0

    def test_empty_repo(self, tmp_path, db_conn):
        repo = tmp_path / "repo"
        repo.mkdir()

        with patch("sentinel.core.indexer.embed_texts", _mock_embed):
            stats = build_index(str(repo), db_conn, "test-model")

        assert stats["files_scanned"] == 0
        assert stats["files_indexed"] == 0

    def test_non_utf8_file(self, tmp_path, db_conn):
        """Non-UTF8 files are read with errors='ignore' and indexed."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "binary.py").write_bytes(b"x = 1\n\x80\x81\x82\n")

        with patch("sentinel.core.indexer.embed_texts", _mock_embed):
            stats = build_index(str(repo), db_conn, "test-model")

        assert stats["files_indexed"] == 1
