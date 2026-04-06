"""Tests for the SQLite state store."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sentinel.models import (
    Evidence,
    EvidenceType,
    Finding,
    FindingStatus,
    ScopeType,
    Severity,
)
from sentinel.store.db import SCHEMA_VERSION, get_connection
from sentinel.store.findings import (
    compare_runs,
    get_finding_by_id,
    get_findings_by_run,
    get_known_fingerprints,
    get_suppressed_fingerprints,
    insert_finding,
    suppress_finding,
    update_finding_status,
)
from sentinel.store.persistence import (
    get_persistence_info,
    update_persistence,
)
from sentinel.store.runs import (
    complete_run,
    create_run,
    get_run_by_id,
    get_run_history,
)


@pytest.fixture
def db_conn():
    """Provide a fresh in-memory database connection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = get_connection(Path(tmpdir) / "test.db")
        yield conn
        conn.close()


def _sample_finding(fingerprint: str = "fp-001") -> Finding:
    return Finding(
        detector="test-detector",
        category="code-quality",
        severity=Severity.MEDIUM,
        confidence=0.8,
        title="Test finding",
        description="Something is wrong",
        evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="bad")],
        file_path="src/x.py",
        line_start=10,
        fingerprint=fingerprint,
    )


def _make_finding(fingerprint: str = "fp-001", title: str = "Test finding") -> Finding:
    return Finding(
        detector="test-detector",
        category="code-quality",
        severity=Severity.MEDIUM,
        confidence=0.8,
        title=title,
        description=f"Finding: {title}",
        evidence=[],
        file_path="src/x.py",
        fingerprint=fingerprint,
    )


class TestDatabase:
    def test_schema_created(self, db_conn):
        tables = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {t["name"] for t in tables}
        assert "runs" in names
        assert "findings" in names
        assert "suppressions" in names
        assert "schema_version" in names
        assert "finding_persistence" in names

    def test_schema_version(self, db_conn):
        row = db_conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert row["version"] == SCHEMA_VERSION

    def test_reopen_same_db(self, tmp_path):
        db_path = tmp_path / "sentinel.db"
        conn1 = get_connection(db_path)
        conn1.close()
        conn2 = get_connection(db_path)
        row = conn2.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert row["version"] == SCHEMA_VERSION
        conn2.close()

    def test_migration_from_v1(self, tmp_path):
        """Simulate a v1 database and verify migration to v2 applies."""
        import sqlite3

        db_path = tmp_path / "old.db"
        # Create a v1-style database manually
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute(
            """CREATE TABLE runs (
                id INTEGER PRIMARY KEY, repo_path TEXT, started_at TEXT,
                completed_at TEXT, scope TEXT DEFAULT 'full', finding_count INTEGER DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE findings (
                id INTEGER PRIMARY KEY, run_id INTEGER, fingerprint TEXT,
                detector TEXT, category TEXT, severity TEXT, confidence REAL,
                title TEXT, description TEXT, file_path TEXT, line_start INTEGER,
                line_end INTEGER, evidence_json TEXT, context_json TEXT,
                status TEXT DEFAULT 'new', created_at TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE suppressions (
                id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE,
                reason TEXT, suppressed_at TEXT
            )"""
        )
        conn.commit()
        conn.close()

        # Reopen via get_connection — migration should apply
        conn2 = get_connection(db_path)
        tables = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {t["name"] for t in tables}
        assert "finding_persistence" in names

        row = conn2.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert row["version"] == SCHEMA_VERSION
        conn2.close()

    def test_migration_from_v2(self, tmp_path):
        """Simulate a v2 database and verify migration to v3 (llm_log) applies."""
        import sqlite3

        db_path = tmp_path / "v2.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.execute(
            """CREATE TABLE runs (
                id INTEGER PRIMARY KEY, repo_path TEXT, started_at TEXT,
                completed_at TEXT, scope TEXT DEFAULT 'full', finding_count INTEGER DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE findings (
                id INTEGER PRIMARY KEY, run_id INTEGER, fingerprint TEXT,
                detector TEXT, category TEXT, severity TEXT, confidence REAL,
                title TEXT, description TEXT, file_path TEXT, line_start INTEGER,
                line_end INTEGER, evidence_json TEXT, context_json TEXT,
                status TEXT DEFAULT 'new', created_at TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE suppressions (
                id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE,
                reason TEXT, suppressed_at TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE finding_persistence (
                fingerprint TEXT PRIMARY KEY, first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL, occurrence_count INTEGER NOT NULL DEFAULT 1
            )"""
        )
        conn.commit()
        conn.close()

        conn2 = get_connection(db_path)
        tables = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {t["name"] for t in tables}
        assert "llm_log" in names

        row = conn2.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert row["version"] == SCHEMA_VERSION
        conn2.close()


class TestRuns:
    def test_create_run(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        assert run.id is not None
        assert run.repo_path == "/tmp/repo"
        assert run.scope == ScopeType.FULL
        assert run.completed_at is None

    def test_complete_run(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        complete_run(db_conn, run.id, finding_count=5)
        updated = get_run_by_id(db_conn, run.id)
        assert updated.completed_at is not None
        assert updated.finding_count == 5

    def test_run_history(self, db_conn):
        create_run(db_conn, "/tmp/repo1")
        create_run(db_conn, "/tmp/repo2")
        create_run(db_conn, "/tmp/repo1")

        all_runs = get_run_history(db_conn)
        assert len(all_runs) == 3

        repo1_runs = get_run_history(db_conn, repo_path="/tmp/repo1")
        assert len(repo1_runs) == 2

    def test_get_nonexistent_run(self, db_conn):
        assert get_run_by_id(db_conn, 999) is None


class TestFindings:
    def test_insert_and_retrieve(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        finding = _sample_finding()
        fid = insert_finding(db_conn, run.id, finding)
        assert fid is not None

        findings = get_findings_by_run(db_conn, run.id)
        assert len(findings) == 1
        assert findings[0].title == "Test finding"
        assert findings[0].fingerprint == "fp-001"
        assert findings[0].severity == Severity.MEDIUM
        assert len(findings[0].evidence) == 1

    def test_timestamp_round_trip(self, db_conn):
        """Finding timestamp should survive DB insert + retrieve (TD-007)."""
        run = create_run(db_conn, "/tmp/repo")
        finding = _sample_finding()
        original_ts = finding.timestamp
        insert_finding(db_conn, run.id, finding)

        retrieved = get_findings_by_run(db_conn, run.id)[0]
        # Should preserve the original timestamp, not generate a new one
        assert retrieved.timestamp.year == original_ts.year
        assert retrieved.timestamp.month == original_ts.month
        assert retrieved.timestamp.day == original_ts.day
        assert retrieved.timestamp.hour == original_ts.hour
        assert retrieved.timestamp.minute == original_ts.minute

    def test_get_by_id(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        fid = insert_finding(db_conn, run.id, _sample_finding())
        found = get_finding_by_id(db_conn, fid)
        assert found is not None
        assert found.title == "Test finding"

    def test_get_nonexistent_finding(self, db_conn):
        assert get_finding_by_id(db_conn, 999) is None

    def test_known_fingerprints(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        insert_finding(db_conn, run.id, _sample_finding("fp-A"))
        insert_finding(db_conn, run.id, _sample_finding("fp-B"))
        fps = get_known_fingerprints(db_conn)
        assert fps == {"fp-A", "fp-B"}


class TestSuppressions:
    def test_suppress_finding(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        insert_finding(db_conn, run.id, _sample_finding("fp-suppress"))
        suppress_finding(db_conn, "fp-suppress", reason="False positive")

        suppressed = get_suppressed_fingerprints(db_conn)
        assert "fp-suppress" in suppressed

        # Check finding status was updated
        findings = get_findings_by_run(db_conn, run.id)
        assert findings[0].status == FindingStatus.SUPPRESSED

    def test_suppress_idempotent(self, db_conn):
        suppress_finding(db_conn, "fp-x", reason="test")
        suppress_finding(db_conn, "fp-x", reason="test again")  # Should not raise
        suppressed = get_suppressed_fingerprints(db_conn)
        assert "fp-x" in suppressed

    def test_update_finding_status(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        fid = insert_finding(db_conn, run.id, _sample_finding())
        update_finding_status(db_conn, fid, FindingStatus.CONFIRMED)
        found = get_finding_by_id(db_conn, fid)
        assert found.status == FindingStatus.CONFIRMED


class TestPersistence:
    def test_first_occurrence(self, db_conn):
        result = update_persistence(db_conn, ["fp-001"])
        assert "fp-001" in result
        assert result["fp-001"].occurrence_count == 1

    def test_multiple_occurrences(self, db_conn):
        update_persistence(db_conn, ["fp-001"])
        update_persistence(db_conn, ["fp-001"])
        result = update_persistence(db_conn, ["fp-001"])
        assert result["fp-001"].occurrence_count == 3

    def test_batch_update(self, db_conn):
        result = update_persistence(db_conn, ["fp-A", "fp-B", "fp-C"])
        assert len(result) == 3
        assert all(info.occurrence_count == 1 for info in result.values())

    def test_mixed_new_and_existing(self, db_conn):
        update_persistence(db_conn, ["fp-A"])
        update_persistence(db_conn, ["fp-A"])
        result = update_persistence(db_conn, ["fp-A", "fp-B"])
        assert result["fp-A"].occurrence_count == 3
        assert result["fp-B"].occurrence_count == 1

    def test_get_persistence_info(self, db_conn):
        update_persistence(db_conn, ["fp-X", "fp-Y"])
        update_persistence(db_conn, ["fp-X"])

        info = get_persistence_info(db_conn, ["fp-X", "fp-Y", "fp-Z"])
        assert "fp-X" in info
        assert info["fp-X"].occurrence_count == 2
        assert "fp-Y" in info
        assert info["fp-Y"].occurrence_count == 1
        assert "fp-Z" not in info  # Never seen

    def test_empty_fingerprints(self, db_conn):
        result = update_persistence(db_conn, [])
        assert result == {}
        info = get_persistence_info(db_conn, [])
        assert info == {}

    def test_timestamps_updated(self, db_conn):
        result1 = update_persistence(db_conn, ["fp-T"])
        first_seen = result1["fp-T"].first_seen

        result2 = update_persistence(db_conn, ["fp-T"])
        # first_seen should not change, last_seen should be >= first
        assert result2["fp-T"].first_seen == first_seen
        assert result2["fp-T"].last_seen >= result2["fp-T"].first_seen


class TestCompareRuns:
    def test_compare_new_resolved_persistent(self, db_conn):
        run1 = create_run(db_conn, "/tmp/repo")
        run2 = create_run(db_conn, "/tmp/repo")

        # Run 1: A, B
        insert_finding(db_conn, run1.id, _make_finding(fingerprint="fp-a", title="A"))
        insert_finding(db_conn, run1.id, _make_finding(fingerprint="fp-b", title="B"))

        # Run 2: B, C
        insert_finding(db_conn, run2.id, _make_finding(fingerprint="fp-b", title="B"))
        insert_finding(db_conn, run2.id, _make_finding(fingerprint="fp-c", title="C"))

        new, resolved, persistent = compare_runs(db_conn, run1.id, run2.id)
        assert len(new) == 1
        assert new[0].title == "C"
        assert len(resolved) == 1
        assert resolved[0].title == "A"
        assert len(persistent) == 1
        assert persistent[0].title == "B"

    def test_compare_identical_runs(self, db_conn):
        run1 = create_run(db_conn, "/tmp/repo")
        run2 = create_run(db_conn, "/tmp/repo")

        for run in [run1, run2]:
            insert_finding(db_conn, run.id, _make_finding(fingerprint="fp-x", title="X"))

        new, resolved, persistent = compare_runs(db_conn, run1.id, run2.id)
        assert len(new) == 0
        assert len(resolved) == 0
        assert len(persistent) == 1

    def test_compare_empty_runs(self, db_conn):
        run1 = create_run(db_conn, "/tmp/repo")
        run2 = create_run(db_conn, "/tmp/repo")

        new, resolved, persistent = compare_runs(db_conn, run1.id, run2.id)
        assert new == []
        assert resolved == []
        assert persistent == []


class TestEvalStore:
    def test_save_and_retrieve(self, db_conn):
        from sentinel.store.eval_store import get_eval_history, save_eval_result
        eid = save_eval_result(
            db_conn,
            repo_path="/tmp/repo",
            total_findings=15,
            true_positives=14,
            false_positives_found=0,
            missing_count=1,
            precision=0.933,
            recall=0.933,
            ground_truth_path="/tmp/repo/gt.toml",
            details={"missing": [{"title": "x"}]},
        )
        assert eid > 0

        results = get_eval_history(db_conn, repo_path="/tmp/repo")
        assert len(results) == 1
        r = results[0]
        assert r.total_findings == 15
        assert r.true_positives == 14
        assert abs(r.precision - 0.933) < 0.001
        assert r.details is not None
        assert r.details["missing"] == [{"title": "x"}]

    def test_multiple_results_ordering(self, db_conn):
        from sentinel.store.eval_store import get_eval_history, save_eval_result
        save_eval_result(db_conn, "/tmp/a", 10, 8, 2, 0, 0.8, 1.0)
        save_eval_result(db_conn, "/tmp/a", 12, 12, 0, 0, 1.0, 1.0)

        results = get_eval_history(db_conn, repo_path="/tmp/a")
        assert len(results) == 2
        # Most recent first
        assert results[0].total_findings == 12
        assert results[1].total_findings == 10

    def test_filter_by_repo(self, db_conn):
        from sentinel.store.eval_store import get_eval_history, save_eval_result
        save_eval_result(db_conn, "/tmp/a", 10, 8, 2, 0, 0.8, 1.0)
        save_eval_result(db_conn, "/tmp/b", 5, 5, 0, 0, 1.0, 1.0)

        a_results = get_eval_history(db_conn, repo_path="/tmp/a")
        assert len(a_results) == 1
        assert a_results[0].repo_path == "/tmp/a"

    def test_to_dict(self, db_conn):
        from sentinel.store.eval_store import get_eval_history, save_eval_result
        save_eval_result(db_conn, "/tmp/r", 10, 10, 0, 0, 1.0, 1.0)
        r = get_eval_history(db_conn)[0]
        d = r.to_dict()
        assert d["precision"] == 1.0
        assert d["recall"] == 1.0
        assert "evaluated_at" in d


# ── Annotation store tests ──────────────────────────────────────────


class TestAnnotations:
    def test_add_and_get(self, db_conn):
        from sentinel.store.findings import add_annotation, get_annotations
        run = create_run(db_conn, "/tmp/test")
        fid = insert_finding(db_conn, run.id, _sample_finding())
        aid = add_annotation(db_conn, fid, "This is a test note")
        assert aid > 0

        annotations = get_annotations(db_conn, fid)
        assert len(annotations) == 1
        assert annotations[0].content == "This is a test note"
        assert annotations[0].finding_id == fid

    def test_multiple_annotations_ordered(self, db_conn):
        from sentinel.store.findings import add_annotation, get_annotations
        run = create_run(db_conn, "/tmp/test")
        fid = insert_finding(db_conn, run.id, _sample_finding())
        add_annotation(db_conn, fid, "First note")
        add_annotation(db_conn, fid, "Second note")
        add_annotation(db_conn, fid, "Third note")

        annotations = get_annotations(db_conn, fid)
        assert len(annotations) == 3
        assert annotations[0].content == "First note"
        assert annotations[2].content == "Third note"

    def test_get_empty(self, db_conn):
        from sentinel.store.findings import get_annotations
        run = create_run(db_conn, "/tmp/test")
        fid = insert_finding(db_conn, run.id, _sample_finding())
        assert get_annotations(db_conn, fid) == []

    def test_delete_annotation(self, db_conn):
        from sentinel.store.findings import add_annotation, delete_annotation, get_annotations
        run = create_run(db_conn, "/tmp/test")
        fid = insert_finding(db_conn, run.id, _sample_finding())
        aid = add_annotation(db_conn, fid, "Delete me")
        assert delete_annotation(db_conn, aid) is True
        assert get_annotations(db_conn, fid) == []

    def test_delete_nonexistent(self, db_conn):
        from sentinel.store.findings import delete_annotation
        assert delete_annotation(db_conn, 9999) is False
