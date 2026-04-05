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
from sentinel.store.db import get_connection
from sentinel.store.findings import (
    get_finding_by_id,
    get_findings_by_run,
    get_known_fingerprints,
    get_suppressed_fingerprints,
    insert_finding,
    suppress_finding,
    update_finding_status,
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

    def test_schema_version(self, db_conn):
        row = db_conn.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == 1

    def test_reopen_same_db(self, tmp_path):
        db_path = tmp_path / "sentinel.db"
        conn1 = get_connection(db_path)
        conn1.close()
        conn2 = get_connection(db_path)
        row = conn2.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == 1
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
