"""Tests for structured LLM interaction logging."""

from __future__ import annotations

from pathlib import Path

from sentinel.models import ScopeType
from sentinel.store.db import get_connection
from sentinel.store.llm_log import (
    LLMLogEntry,
    get_llm_log_entries,
    get_llm_log_filters,
    get_llm_log_for_run,
    get_llm_log_stats,
    get_model_speed_stats,
    insert_llm_log,
)
from sentinel.store.runs import create_run


def _make_conn(tmp_path: Path):
    return get_connection(tmp_path / "test.db")


class TestInsertAndRetrieve:
    def test_insert_and_retrieve(self, tmp_path):
        conn = _make_conn(tmp_path)
        run = create_run(conn, "/repo", ScopeType.FULL)

        entry = LLMLogEntry(
            purpose="judge",
            model="qwen3.5:4b",
            detector="todo-scanner",
            finding_fingerprint="abc123",
            finding_title="TODO: fix this",
            prompt="Judge this finding...",
            response='{"is_real": true, "adjusted_severity": "medium"}',
            tokens_generated=42,
            generation_ms=1200.5,
            verdict="confirmed",
            is_real=True,
            adjusted_severity="medium",
            summary="Real issue worth fixing",
        )
        insert_llm_log(conn, run.id, entry)

        rows = get_llm_log_for_run(conn, run.id)
        assert len(rows) == 1
        row = rows[0]
        assert row["purpose"] == "judge"
        assert row["model"] == "qwen3.5:4b"
        assert row["detector"] == "todo-scanner"
        assert row["finding_fingerprint"] == "abc123"
        assert row["finding_title"] == "TODO: fix this"
        assert row["prompt"] == "Judge this finding..."
        assert row["tokens_generated"] == 42
        assert row["generation_ms"] == 1200.5
        assert row["verdict"] == "confirmed"
        assert row["is_real"] == 1
        assert row["adjusted_severity"] == "medium"
        assert row["summary"] == "Real issue worth fixing"
        assert row["timestamp"] is not None

    def test_insert_minimal_entry(self, tmp_path):
        conn = _make_conn(tmp_path)
        entry = LLMLogEntry(
            purpose="doc-code-comparison",
            model="qwen3.5:4b",
            prompt="Compare these...",
        )
        insert_llm_log(conn, None, entry)

        rows = conn.execute("SELECT * FROM llm_log").fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["run_id"] is None
        assert row["purpose"] == "doc-code-comparison"
        assert row["detector"] is None
        assert row["verdict"] is None

    def test_multiple_entries_for_run(self, tmp_path):
        conn = _make_conn(tmp_path)
        run = create_run(conn, "/repo", ScopeType.FULL)

        for i in range(5):
            insert_llm_log(conn, run.id, LLMLogEntry(
                purpose="judge",
                model="qwen3.5:4b",
                prompt=f"Prompt {i}",
                verdict="confirmed" if i % 2 == 0 else "likely_false_positive",
                is_real=i % 2 == 0,
            ))

        rows = get_llm_log_for_run(conn, run.id)
        assert len(rows) == 5


class TestStats:
    def test_stats_for_run(self, tmp_path):
        conn = _make_conn(tmp_path)
        run = create_run(conn, "/repo", ScopeType.FULL)

        insert_llm_log(conn, run.id, LLMLogEntry(
            purpose="judge", model="qwen3.5:4b", prompt="p1",
            verdict="confirmed", tokens_generated=50, generation_ms=1000,
        ))
        insert_llm_log(conn, run.id, LLMLogEntry(
            purpose="judge", model="qwen3.5:4b", prompt="p2",
            verdict="likely_false_positive", tokens_generated=30, generation_ms=800,
        ))
        insert_llm_log(conn, run.id, LLMLogEntry(
            purpose="doc-code-comparison", model="qwen3.5:4b", prompt="p3",
            verdict="accurate", tokens_generated=20, generation_ms=500,
        ))

        stats = get_llm_log_stats(conn, run.id)
        assert stats["total_calls"] == 3
        assert stats["judge_calls"] == 2
        assert stats["doc_code_calls"] == 1
        assert stats["confirmed"] == 1
        assert stats["likely_fp"] == 1
        assert stats["accurate"] == 1
        assert stats["total_tokens"] == 100
        assert stats["total_generation_ms"] == 2300

    def test_stats_all_runs(self, tmp_path):
        conn = _make_conn(tmp_path)
        run1 = create_run(conn, "/repo", ScopeType.FULL)
        run2 = create_run(conn, "/repo", ScopeType.FULL)

        insert_llm_log(conn, run1.id, LLMLogEntry(
            purpose="judge", model="qwen3.5:4b", prompt="p1", verdict="confirmed",
        ))
        insert_llm_log(conn, run2.id, LLMLogEntry(
            purpose="judge", model="qwen3.5:4b", prompt="p2", verdict="error",
        ))

        stats = get_llm_log_stats(conn)
        assert stats["total_calls"] == 2
        assert stats["confirmed"] == 1
        assert stats["errors"] == 1

    def test_stats_empty(self, tmp_path):
        conn = _make_conn(tmp_path)
        stats = get_llm_log_stats(conn)
        assert stats["total_calls"] == 0


class TestFalsePositiveTracking:
    def test_is_real_boolean_mapping(self, tmp_path):
        """is_real=True→1, is_real=False→0, is_real=None→NULL."""
        conn = _make_conn(tmp_path)
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m", prompt="p", is_real=True,
        ))
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m", prompt="p", is_real=False,
        ))
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m", prompt="p", is_real=None,
        ))

        rows = conn.execute("SELECT is_real FROM llm_log ORDER BY id").fetchall()
        assert rows[0]["is_real"] == 1
        assert rows[1]["is_real"] == 0
        assert rows[2]["is_real"] is None


class TestModelSpeedStats:
    def test_empty_table(self, tmp_path):
        conn = _make_conn(tmp_path)
        result = get_model_speed_stats(conn)
        assert result == {}

    def test_multiple_models(self, tmp_path):
        conn = _make_conn(tmp_path)
        # Model A: 100 tokens in 2000ms = 50 tok/s
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="qwen3.5:4b", prompt="p1",
            tokens_generated=60, generation_ms=1000,
        ))
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="qwen3.5:4b", prompt="p2",
            tokens_generated=40, generation_ms=1000,
        ))
        # Model B: 200 tokens in 2000ms = 100 tok/s
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="gpt-5.4-nano", prompt="p3",
            tokens_generated=200, generation_ms=2000,
        ))

        result = get_model_speed_stats(conn)
        assert "qwen3.5:4b" in result
        assert "gpt-5.4-nano" in result

        qwen = result["qwen3.5:4b"]
        assert qwen["calls"] == 2
        assert qwen["total_tokens"] == 100
        assert qwen["avg_tok_s"] == 50.0

        nano = result["gpt-5.4-nano"]
        assert nano["calls"] == 1
        assert nano["total_tokens"] == 200
        assert nano["avg_tok_s"] == 100.0

    def test_null_and_zero_excluded(self, tmp_path):
        """Rows with NULL or zero generation_ms are excluded."""
        conn = _make_conn(tmp_path)
        # Valid row
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p",
            tokens_generated=50, generation_ms=1000,
        ))
        # NULL tokens_generated — excluded
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p",
            tokens_generated=None, generation_ms=500,
        ))
        # NULL generation_ms — excluded
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p",
            tokens_generated=30, generation_ms=None,
        ))

        result = get_model_speed_stats(conn)
        assert result["m1"]["calls"] == 1
        assert result["m1"]["total_tokens"] == 50
        assert result["m1"]["avg_tok_s"] == 50.0


class TestGetLLMLogEntries:
    """Tests for the paginated, filtered query function."""

    def test_returns_all_when_no_filters(self, tmp_path):
        conn = _make_conn(tmp_path)
        for i in range(3):
            insert_llm_log(conn, None, LLMLogEntry(
                purpose="judge", model="m1", prompt=f"p{i}",
                detector="d1", verdict="confirmed",
            ))
        entries, total = get_llm_log_entries(conn)
        assert total == 3
        assert len(entries) == 3

    def test_filter_by_detector(self, tmp_path):
        conn = _make_conn(tmp_path)
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p1",
            detector="todo-scanner", verdict="confirmed",
        ))
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p2",
            detector="lint-runner", verdict="error",
        ))
        entries, total = get_llm_log_entries(conn, detector="todo-scanner")
        assert total == 1
        assert entries[0]["detector"] == "todo-scanner"

    def test_filter_by_verdict(self, tmp_path):
        conn = _make_conn(tmp_path)
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p1",
            detector="d1", verdict="confirmed",
        ))
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p2",
            detector="d2", verdict="error",
        ))
        entries, total = get_llm_log_entries(conn, verdict="error")
        assert total == 1
        assert entries[0]["verdict"] == "error"

    def test_filter_by_model(self, tmp_path):
        conn = _make_conn(tmp_path)
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="qwen3.5:4b", prompt="p1",
            detector="d1", verdict="confirmed",
        ))
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="gpt-5.4-nano", prompt="p2",
            detector="d1", verdict="confirmed",
        ))
        entries, total = get_llm_log_entries(conn, model="qwen3.5:4b")
        assert total == 1
        assert entries[0]["model"] == "qwen3.5:4b"

    def test_filter_by_run_id(self, tmp_path):
        conn = _make_conn(tmp_path)
        run1 = create_run(conn, str(tmp_path / "repo1"))
        run2 = create_run(conn, str(tmp_path / "repo2"))
        insert_llm_log(conn, run1.id, LLMLogEntry(
            purpose="judge", model="m1", prompt="p1",
            detector="d1", verdict="confirmed",
        ))
        insert_llm_log(conn, run2.id, LLMLogEntry(
            purpose="judge", model="m1", prompt="p2",
            detector="d1", verdict="error",
        ))
        entries, total = get_llm_log_entries(conn, run_id=run1.id)
        assert total == 1
        assert entries[0]["run_id"] == run1.id

    def test_pagination(self, tmp_path):
        conn = _make_conn(tmp_path)
        for i in range(5):
            insert_llm_log(conn, None, LLMLogEntry(
                purpose="judge", model="m1", prompt=f"p{i}",
                detector="d1", verdict="confirmed",
            ))
        entries, total = get_llm_log_entries(conn, limit=2, offset=0)
        assert total == 5
        assert len(entries) == 2

        entries2, total2 = get_llm_log_entries(conn, limit=2, offset=2)
        assert total2 == 5
        assert len(entries2) == 2
        assert entries[0]["id"] != entries2[0]["id"]


class TestGetLLMLogFilters:
    """Tests for the filter dropdown helper."""

    def test_returns_distinct_values(self, tmp_path):
        conn = _make_conn(tmp_path)
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m1", prompt="p1",
            detector="d1", verdict="confirmed",
        ))
        insert_llm_log(conn, None, LLMLogEntry(
            purpose="judge", model="m2", prompt="p2",
            detector="d2", verdict="error",
        ))
        filters = get_llm_log_filters(conn)
        assert sorted(filters["detectors"]) == ["d1", "d2"]
        assert sorted(filters["models"]) == ["m1", "m2"]
        assert sorted(filters["verdicts"]) == ["confirmed", "error"]

    def test_empty_database(self, tmp_path):
        conn = _make_conn(tmp_path)
        filters = get_llm_log_filters(conn)
        assert filters["detectors"] == []
        assert filters["models"] == []
        assert filters["verdicts"] == []
