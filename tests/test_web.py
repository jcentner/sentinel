"""Tests for the Sentinel web UI."""

from __future__ import annotations

import sqlite3

import pytest
from starlette.testclient import TestClient

from sentinel.models import (
    Evidence,
    EvidenceType,
    Finding,
    FindingStatus,
    Severity,
)
from sentinel.store.db import get_connection
from sentinel.store.findings import get_finding_by_id, insert_finding
from sentinel.store.runs import complete_run, create_run
from sentinel.web.app import create_app


@pytest.fixture()
def db_conn() -> sqlite3.Connection:
    """In-memory DB with schema applied."""
    conn = get_connection(":memory:", check_same_thread=False)
    return conn


@pytest.fixture()
def app(db_conn: sqlite3.Connection) -> TestClient:
    """Starlette test client with an in-memory DB."""
    application = create_app(db_conn)
    return TestClient(application)


@pytest.fixture()
def seeded_db(db_conn: sqlite3.Connection) -> tuple[sqlite3.Connection, int, int]:
    """DB with one run and two findings; returns (conn, run_id, finding_id)."""
    run = create_run(db_conn, "/tmp/test-repo")
    f1 = Finding(
        detector="todo-scanner",
        category="maintainability",
        severity=Severity.MEDIUM,
        confidence=0.9,
        title="TODO found in main.py",
        description="Unresolved TODO comment",
        evidence=[Evidence(type=EvidenceType.CODE, content="# TODO: fix this", source="main.py")],
        file_path="main.py",
        line_start=10,
        fingerprint="fp-abc",
    )
    f2 = Finding(
        detector="lint-runner",
        category="code-quality",
        severity=Severity.HIGH,
        confidence=0.95,
        title="Unused import os",
        description="Module os is imported but unused",
        evidence=[Evidence(type=EvidenceType.LINT_OUTPUT, content="F401 unused import", source="ruff")],
        file_path="utils.py",
        line_start=1,
        fingerprint="fp-def",
    )
    fid1 = insert_finding(db_conn, run.id, f1)
    insert_finding(db_conn, run.id, f2)
    complete_run(db_conn, run.id, 2)
    return db_conn, run.id, fid1


@pytest.fixture()
def seeded_app(seeded_db: tuple[sqlite3.Connection, int, int]) -> tuple[TestClient, int, int]:
    """Test client with seeded data; returns (client, run_id, finding_id)."""
    conn, run_id, finding_id = seeded_db
    application = create_app(conn)
    return TestClient(application), run_id, finding_id


# ── Route tests ──────────────────────────────────────────────────────


class TestIndexRoute:
    def test_empty_state(self, app: TestClient) -> None:
        resp = app.get("/", follow_redirects=False)
        # No runs → shows empty state page (200)
        assert resp.status_code == 200
        assert "No scan runs yet" in resp.text

    def test_redirect_to_latest_run(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, run_id, _ = seeded_app
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert f"/runs/{run_id}" in resp.headers["location"]


class TestRunsList:
    def test_empty(self, app: TestClient) -> None:
        resp = app.get("/runs")
        assert resp.status_code == 200
        assert "No scan runs yet" in resp.text

    def test_with_runs(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, _ = seeded_app
        resp = client.get("/runs")
        assert resp.status_code == 200
        assert f"/runs/{run_id}" in resp.text
        assert "/tmp/test-repo" in resp.text


class TestRunDetail:
    def test_not_found(self, app: TestClient) -> None:
        resp = app.get("/runs/9999")
        assert resp.status_code == 404

    def test_shows_findings(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, _ = seeded_app
        resp = client.get(f"/runs/{run_id}")
        assert resp.status_code == 200
        assert "TODO found in main.py" in resp.text
        assert "Unused import os" in resp.text

    def test_severity_grouping(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, _ = seeded_app
        resp = client.get(f"/runs/{run_id}")
        assert "high" in resp.text.lower()
        assert "medium" in resp.text.lower()


class TestFindingDetail:
    def test_not_found(self, app: TestClient) -> None:
        resp = app.get("/findings/9999")
        assert resp.status_code == 404

    def test_shows_detail(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, _, finding_id = seeded_app
        resp = client.get(f"/findings/{finding_id}")
        assert resp.status_code == 200
        assert "TODO found in main.py" in resp.text
        assert "todo-scanner" in resp.text
        assert "main.py" in resp.text
        assert "fp-abc" in resp.text

    def test_shows_evidence(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, _, finding_id = seeded_app
        resp = client.get(f"/findings/{finding_id}")
        assert "# TODO: fix this" in resp.text


class TestFindingActions:
    def test_approve(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/action",
            data={"action": "approve"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_approve_htmx(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/action",
            data={"action": "approve"},
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "approved" in resp.text

    def test_suppress(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/action",
            data={"action": "suppress", "reason": "not relevant"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_suppress_htmx(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/action",
            data={"action": "suppress"},
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "suppressed" in resp.text

    def test_unknown_action(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/action",
            data={"action": "bogus"},
        )
        assert resp.status_code == 400

    def test_action_not_found(self, app: TestClient) -> None:
        resp = app.post(
            "/findings/9999/action",
            data={"action": "approve"},
        )
        assert resp.status_code == 404

    def test_approve_updates_db(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        conn, _, finding_id = seeded_db
        application = create_app(conn)
        client = TestClient(application)
        client.post(
            f"/findings/{finding_id}/action",
            data={"action": "approve"},
            follow_redirects=False,
        )
        finding = get_finding_by_id(conn, finding_id)
        assert finding is not None
        assert finding.status == FindingStatus.APPROVED


class TestStaticFiles:
    def test_css_served(self, app: TestClient) -> None:
        resp = app.get("/static/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]
