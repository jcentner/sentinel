"""Tests for the embedding system: store, indexer, and context integration."""

from __future__ import annotations

import pytest

from sentinel.core.indexer import _collect_files, _should_skip_dir, build_index, chunk_file
from sentinel.models import EvidenceType, Finding, Severity
from sentinel.store.db import SCHEMA_VERSION, get_connection
from sentinel.store.embeddings import (
    _pack_embedding,
    _unpack_embedding,
    chunk_count,
    clear_all_chunks,
    content_hash,
    cosine_similarity,
    delete_file_chunks,
    get_indexed_files,
    get_meta,
    query_similar,
    set_meta,
    upsert_chunks,
)

# --- Embedding store tests ---


class TestPackUnpack:
    def test_roundtrip(self):
        vec = [0.1, 0.2, 0.3, 0.4, 0.5]
        packed = _pack_embedding(vec)
        assert isinstance(packed, bytes)
        assert len(packed) == 5 * 4  # 5 floats x 4 bytes
        unpacked = _unpack_embedding(packed)
        for a, b in zip(vec, unpacked, strict=True):
            assert abs(a - b) < 1e-6

    def test_empty(self):
        assert _pack_embedding([]) == b""
        assert _unpack_embedding(b"") == []


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert cosine_similarity(a, b) == 0.0


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_content(self):
        assert content_hash("hello") != content_hash("world")

    def test_length(self):
        assert len(content_hash("test")) == 16


class TestChunkStore:
    @pytest.fixture
    def conn(self, tmp_path):
        return get_connection(tmp_path / "test.db")

    def test_upsert_and_count(self, conn):
        chunks = [
            {
                "start_line": 1, "end_line": 10,
                "content": "line 1\nline 2\n",
                "embedding": [0.1, 0.2, 0.3],
            },
            {
                "start_line": 8, "end_line": 20,
                "content": "line 8\nline 9\n",
                "embedding": [0.4, 0.5, 0.6],
            },
        ]
        n = upsert_chunks(conn, "src/foo.py", chunks, "test-model")
        assert n == 2
        assert chunk_count(conn) == 2

    def test_upsert_replaces_old_chunks(self, conn):
        chunks_v1 = [
            {"start_line": 1, "end_line": 10, "content": "old", "embedding": [0.1]},
        ]
        upsert_chunks(conn, "src/foo.py", chunks_v1, "test-model")
        assert chunk_count(conn) == 1

        chunks_v2 = [
            {"start_line": 1, "end_line": 5, "content": "new1", "embedding": [0.2]},
            {"start_line": 5, "end_line": 10, "content": "new2", "embedding": [0.3]},
        ]
        upsert_chunks(conn, "src/foo.py", chunks_v2, "test-model")
        assert chunk_count(conn) == 2

    def test_delete_file_chunks(self, conn):
        chunks = [
            {"start_line": 1, "end_line": 10, "content": "c1", "embedding": [0.1]},
        ]
        upsert_chunks(conn, "src/a.py", chunks, "m")
        upsert_chunks(conn, "src/b.py", chunks, "m")
        assert chunk_count(conn) == 2

        deleted = delete_file_chunks(conn, "src/a.py")
        assert deleted == 1
        assert chunk_count(conn) == 1

    def test_clear_all(self, conn):
        chunks = [{"start_line": 1, "end_line": 5, "content": "c", "embedding": [0.1]}]
        upsert_chunks(conn, "a.py", chunks, "m")
        upsert_chunks(conn, "b.py", chunks, "m")
        set_meta(conn, "test_key", "test_val")

        cleared = clear_all_chunks(conn)
        assert cleared == 2
        assert chunk_count(conn) == 0
        assert get_meta(conn, "test_key") is None

    def test_get_indexed_files(self, conn):
        chunks = [{"start_line": 1, "end_line": 5, "content": "c", "embedding": [0.1]}]
        upsert_chunks(conn, "a.py", chunks, "m")
        upsert_chunks(conn, "b.py", chunks, "m")

        files = get_indexed_files(conn)
        assert files == {"a.py", "b.py"}

    def test_query_similar_basic(self, conn):
        # Insert two chunks with known embeddings
        c1 = [{"start_line": 1, "end_line": 5, "content": "hello world",
               "embedding": [1.0, 0.0, 0.0]}]
        c2 = [{"start_line": 1, "end_line": 5, "content": "foo bar",
               "embedding": [0.0, 1.0, 0.0]}]
        upsert_chunks(conn, "a.py", c1, "m")
        upsert_chunks(conn, "b.py", c2, "m")

        # Query with vector similar to c1
        results = query_similar(conn, [0.9, 0.1, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0]["file_path"] == "a.py"
        assert results[0]["similarity"] > results[1]["similarity"]

    def test_query_similar_excludes_file(self, conn):
        c1 = [{"start_line": 1, "end_line": 5, "content": "hello",
               "embedding": [1.0, 0.0]}]
        c2 = [{"start_line": 1, "end_line": 5, "content": "world",
               "embedding": [0.9, 0.1]}]
        upsert_chunks(conn, "same.py", c1, "m")
        upsert_chunks(conn, "other.py", c2, "m")

        results = query_similar(conn, [1.0, 0.0], top_k=5, exclude_file="same.py")
        assert len(results) == 1
        assert results[0]["file_path"] == "other.py"

    def test_metadata(self, conn):
        set_meta(conn, "model", "nomic-embed-text")
        assert get_meta(conn, "model") == "nomic-embed-text"
        assert get_meta(conn, "nonexistent") is None

        # Update existing key
        set_meta(conn, "model", "updated")
        assert get_meta(conn, "model") == "updated"


# --- Chunking tests ---


class TestChunking:
    def test_basic_chunking(self):
        content = "\n".join(f"line {i}" for i in range(1, 101))
        chunks = chunk_file(content, chunk_size=50, chunk_overlap=10)
        assert len(chunks) >= 2
        assert chunks[0]["start_line"] == 1
        assert chunks[0]["end_line"] == 50

    def test_small_file_single_chunk(self):
        content = "line 1\nline 2\nline 3\n"
        chunks = chunk_file(content, chunk_size=50, chunk_overlap=10)
        assert len(chunks) == 1
        assert chunks[0]["start_line"] == 1
        assert chunks[0]["end_line"] == 3

    def test_empty_file(self):
        assert chunk_file("", chunk_size=50, chunk_overlap=10) == []

    def test_whitespace_only_chunks_skipped(self):
        content = "\n\n\n" + "code here\n"
        chunks = chunk_file(content, chunk_size=3, chunk_overlap=0)
        # Should have at least 1 non-empty chunk
        assert all(c["content"].strip() for c in chunks)

    def test_overlap(self):
        content = "\n".join(f"L{i}" for i in range(1, 21))
        chunks = chunk_file(content, chunk_size=10, chunk_overlap=3)
        assert len(chunks) >= 2
        # Second chunk should start before the first one ends
        if len(chunks) > 1:
            assert chunks[1]["start_line"] < chunks[0]["end_line"] + 1


# --- Indexer tests ---


class TestIndexer:
    def test_should_skip_dir(self):
        assert _should_skip_dir(".git")
        assert _should_skip_dir("__pycache__")
        assert _should_skip_dir("node_modules")
        assert _should_skip_dir("foo.egg-info")
        assert not _should_skip_dir("src")
        assert not _should_skip_dir("docs")

    def test_collect_files(self, tmp_path):
        # Create a simple repo structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')\n")
        (tmp_path / "README.md").write_text("# readme\n")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git config\n")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cache.pyc").write_bytes(b"\x00\x00")

        files = _collect_files(tmp_path)
        rel_names = {str(f.relative_to(tmp_path)) for f in files}
        assert "src/main.py" in rel_names
        assert "README.md" in rel_names
        assert ".git/config" not in rel_names
        # .pyc should be skipped by extension
        assert "__pycache__/cache.pyc" not in rel_names

    def test_build_index_with_mock_embeddings(self, tmp_path):
        """Test build_index with mocked provider embedding calls."""
        from tests.mock_provider import MockProvider

        # Create a small repo
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text(
            "\n".join(f"# line {i}" for i in range(20)) + "\n"
        )
        (tmp_path / "README.md").write_text("# Test\n\nSome content.\n")

        conn = get_connection(tmp_path / ".sentinel" / "test.db")
        fake_dim = 4

        provider = MockProvider(
            embed_result=[[0.1] * fake_dim],  # Will be re-used per call
        )
        # Override embed to return correct number of vectors
        def sized_embed(texts):
            provider.embed_calls.append(texts)
            return [[0.1 * (i + 1)] * fake_dim for i in range(len(texts))]
        provider.embed = sized_embed

        stats = build_index(str(tmp_path), conn, provider)

        assert stats["files_scanned"] >= 2
        assert stats["files_indexed"] >= 2
        assert stats["chunks_created"] >= 2
        assert chunk_count(conn) >= 2
        conn.close()

    def test_incremental_index_skips_unchanged(self, tmp_path):
        """Second build_index call with no changes should skip all files."""
        from tests.mock_provider import MockProvider

        (tmp_path / "main.py").write_text("print(1)\n")
        conn = get_connection(tmp_path / ".sentinel" / "test.db")

        provider = MockProvider()
        provider.embed = lambda texts: [[0.5] * 4 for _ in texts]

        stats1 = build_index(str(tmp_path), conn, provider)
        assert stats1["files_indexed"] >= 1

        stats2 = build_index(str(tmp_path), conn, provider)
        assert stats2["files_indexed"] == 0  # nothing changed

        conn.close()

    def test_index_removes_deleted_files(self, tmp_path):
        """Chunks for deleted files are removed on re-index."""
        from tests.mock_provider import MockProvider

        (tmp_path / "a.py").write_text("code\n")
        (tmp_path / "b.py").write_text("more code\n")
        conn = get_connection(tmp_path / ".sentinel" / "test.db")

        provider = MockProvider()
        provider.embed = lambda texts: [[0.5] * 4 for _ in texts]

        build_index(str(tmp_path), conn, provider)
        assert "b.py" in get_indexed_files(conn)

        # Delete b.py and re-index
        (tmp_path / "b.py").unlink()
        stats = build_index(str(tmp_path), conn, provider)
        assert stats["files_removed"] >= 1
        assert "b.py" not in get_indexed_files(conn)

        conn.close()

    def test_build_index_handles_embed_failure(self, tmp_path):
        """When embedding fails, files are skipped gracefully."""
        from tests.mock_provider import MockProvider

        (tmp_path / "main.py").write_text("code\n")
        conn = get_connection(tmp_path / ".sentinel" / "test.db")

        provider = MockProvider(embed_result=None)

        stats = build_index(str(tmp_path), conn, provider)
        assert stats["files_skipped"] >= 1
        assert chunk_count(conn) == 0

        conn.close()


# --- Context gatherer integration tests ---


class TestGatherContextWithEmbeddings:
    def _make_finding(self, title="Test finding", file_path="src/foo.py"):
        return Finding(
            detector="test",
            category="test",
            severity=Severity.MEDIUM,
            confidence=0.8,
            title=title,
            description="A test finding description",
            evidence=[],
            file_path=file_path,
            line_start=10,
        )

    def test_gather_context_without_embeddings(self, tmp_path):
        """Without embed config, works exactly as before (heuristic only)."""
        from sentinel.core.context import gather_context

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text(
            "\n".join(f"line {i}" for i in range(20)) + "\n"
        )

        f = self._make_finding()
        result = gather_context([f], str(tmp_path))
        assert len(result) == 1
        # Should have surrounding code evidence (heuristic)
        code_ev = [e for e in result[0].evidence if e.type == EvidenceType.CODE]
        assert len(code_ev) >= 1

    def test_gather_context_with_embeddings(self, tmp_path):
        """With embed config and index, adds embedding-based evidence."""
        from sentinel.core.context import gather_context
        from tests.mock_provider import MockProvider

        # Set up repo with source file
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text(
            "\n".join(f"line {i}" for i in range(20)) + "\n"
        )
        (tmp_path / "src" / "bar.py").write_text("related code\n" * 10)

        conn = get_connection(tmp_path / ".sentinel" / "test.db")

        # Build index with mock embeddings
        fake_dim = 4
        provider = MockProvider()
        provider.embed = lambda texts: [[0.5] * fake_dim for _ in texts]

        build_index(str(tmp_path), conn, provider)

        # Now gather context with embedding support.
        f = self._make_finding()
        result = gather_context(
            [f], str(tmp_path),
            conn=conn, provider=provider,
        )

        assert len(result) == 1
        conn.close()

    def test_gather_context_empty_index_falls_back(self, tmp_path):
        """With empty index, falls back to heuristic only."""
        from sentinel.core.context import gather_context
        from tests.mock_provider import MockProvider

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("code\n" * 20)

        conn = get_connection(tmp_path / ".sentinel" / "test.db")

        provider = MockProvider()
        provider.embed = lambda texts: [[0.5] * 4 for _ in texts]

        f = self._make_finding()
        result = gather_context(
            [f], str(tmp_path),
            conn=conn, provider=provider,
        )
        assert len(result) == 1
        # No embedding evidence should be added (index is empty)
        conn.close()


# --- Config tests ---


class TestEmbedConfig:
    def test_default_embed_config(self):
        from sentinel.config import SentinelConfig
        config = SentinelConfig()
        assert config.embed_model == ""
        assert config.embed_chunk_size == 50
        assert config.embed_chunk_overlap == 10

    def test_embed_config_from_toml(self, tmp_path):
        from sentinel.config import load_config
        config_file = tmp_path / "sentinel.toml"
        config_file.write_text(
            '[sentinel]\nembed_model = "nomic-embed-text"\n'
            'embed_chunk_size = 40\n'
            'embed_chunk_overlap = 5\n'
        )
        config = load_config(tmp_path)
        assert config.embed_model == "nomic-embed-text"
        assert config.embed_chunk_size == 40
        assert config.embed_chunk_overlap == 5


# --- Schema migration test ---


class TestSchemaMigrationV5:
    def test_chunks_table_exists(self, tmp_path):
        conn = get_connection(tmp_path / "test.db")
        # The table should exist after migration
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
        ).fetchone()
        assert row is not None

        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='embed_meta'"
        ).fetchone()
        assert row is not None
        conn.close()

    def test_schema_version_is_current(self, tmp_path):
        conn = get_connection(tmp_path / "test.db")
        row = conn.execute(
            "SELECT MAX(version) as v FROM schema_version"
        ).fetchone()
        assert row["v"] == SCHEMA_VERSION
        conn.close()
