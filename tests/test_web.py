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
from sentinel.store.findings import get_finding_by_id, insert_finding, update_finding_status
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

    def test_filter_by_severity(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, _ = seeded_app
        resp = client.get(f"/runs/{run_id}?severity=high")
        assert resp.status_code == 200
        assert "Unused import os" in resp.text
        assert "TODO found in main.py" not in resp.text

    def test_filter_by_detector(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, _ = seeded_app
        resp = client.get(f"/runs/{run_id}?detector=todo-scanner")
        assert resp.status_code == 200
        assert "TODO found in main.py" in resp.text
        assert "Unused import os" not in resp.text

    def test_filter_by_status(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, _ = seeded_app
        # All findings are 'new' by default
        resp = client.get(f"/runs/{run_id}?status=new")
        assert resp.status_code == 200
        assert "TODO found in main.py" in resp.text

    def test_filter_no_match(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, _ = seeded_app
        resp = client.get(f"/runs/{run_id}?severity=critical")
        assert resp.status_code == 200
        assert "No findings match" in resp.text


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


class TestScanTrigger:
    def test_no_repo_configured(self, app: TestClient) -> None:
        resp = app.post("/scan", follow_redirects=False)
        assert resp.status_code == 500
        assert "No repo configured" in resp.text

    def test_scan_success(
        self, seeded_db: tuple[sqlite3.Connection, int, int], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock

        from sentinel.models import RunSummary

        conn, _run_id, _ = seeded_db
        application = create_app(conn, repo_path="/tmp/test-repo")
        client = TestClient(application)

        mock_run = RunSummary(id=42, repo_path="/tmp/test-repo")
        monkeypatch.setattr(
            "sentinel.core.runner.run_scan",
            MagicMock(return_value=(mock_run, [], "/dev/null")),
        )
        mock_config = MagicMock()
        mock_config.model = "test"
        mock_config.ollama_url = "http://localhost:11434"
        mock_config.skip_judge = True
        monkeypatch.setattr("sentinel.config.load_config", MagicMock(return_value=mock_config))

        resp = client.post("/scan", follow_redirects=False)
        assert resp.status_code == 303
        assert "/runs/42" in resp.headers["location"]

    def test_scan_htmx(
        self, seeded_db: tuple[sqlite3.Connection, int, int], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock

        from sentinel.models import RunSummary

        conn, _, _ = seeded_db
        application = create_app(conn, repo_path="/tmp/test-repo")
        client = TestClient(application)

        mock_run = RunSummary(id=7, repo_path="/tmp/test-repo")
        monkeypatch.setattr(
            "sentinel.core.runner.run_scan",
            MagicMock(return_value=(mock_run, [], "/dev/null")),
        )
        mock_config = MagicMock()
        mock_config.model = "test"
        mock_config.ollama_url = "http://localhost:11434"
        mock_config.skip_judge = True
        monkeypatch.setattr("sentinel.config.load_config", MagicMock(return_value=mock_config))

        resp = client.post("/scan", headers={"hx-request": "true"})
        assert resp.status_code == 200
        assert "/runs/7" in resp.text
        assert "Scan complete" in resp.text

    def test_scan_failure(
        self, seeded_db: tuple[sqlite3.Connection, int, int], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock

        conn, _, _ = seeded_db
        application = create_app(conn, repo_path="/tmp/test-repo")
        client = TestClient(application)

        monkeypatch.setattr(
            "sentinel.core.runner.run_scan",
            MagicMock(side_effect=RuntimeError("Ollama not available")),
        )
        mock_config = MagicMock()
        mock_config.model = "test"
        mock_config.ollama_url = "http://localhost:11434"
        mock_config.skip_judge = True
        monkeypatch.setattr("sentinel.config.load_config", MagicMock(return_value=mock_config))

        resp = client.post("/scan", follow_redirects=False)
        assert resp.status_code == 500
        assert "Scan failed" in resp.text


class TestSecurityGuards:
    def test_open_redirect_blocked(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        """External referer should redirect to / not to the external URL."""
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/action",
            data={"action": "approve"},
            headers={"referer": "https://evil.example.com/steal"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_empty_fingerprint_suppress_blocked(
        self, db_conn: sqlite3.Connection
    ) -> None:
        """Suppress should fail if finding has empty fingerprint."""
        run = create_run(db_conn, "/tmp/test")
        f = Finding(
            detector="test",
            category="test",
            severity=Severity.LOW,
            confidence=0.5,
            title="No fingerprint",
            description="Test",
            evidence=[Evidence(type=EvidenceType.CODE, content="x", source="test")],
            fingerprint="",
        )
        fid = insert_finding(db_conn, run.id, f)
        complete_run(db_conn, run.id, 1)

        application = create_app(db_conn)
        client = TestClient(application)
        resp = client.post(
            f"/findings/{fid}/action",
            data={"action": "suppress"},
        )
        assert resp.status_code == 400
        assert "no fingerprint" in resp.text.lower()


class TestScanForm:
    def test_scan_form_get(self, app: TestClient) -> None:
        resp = app.get("/scan")
        assert resp.status_code == 200
        assert "Repository Path" in resp.text

    def test_scan_form_with_repo(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        conn, _, _ = seeded_db
        application = create_app(conn, repo_path="/tmp/test-repo")
        client = TestClient(application)
        resp = client.get("/scan")
        assert resp.status_code == 200
        assert "/tmp/test-repo" in resp.text


class TestGitHubPage:
    def test_github_page_empty(self, app: TestClient) -> None:
        resp = app.get("/github")
        assert resp.status_code == 200
        assert "No approved findings" in resp.text

    def test_github_page_with_approved(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        conn, _, finding_id = seeded_db
        update_finding_status(conn, finding_id, FindingStatus.APPROVED)

        application = create_app(conn)
        client = TestClient(application)
        resp = client.get("/github")
        assert resp.status_code == 200
        assert "Approved Findings" in resp.text
        assert "TODO found in main.py" in resp.text

    def test_github_dry_run(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        conn, _, finding_id = seeded_db
        update_finding_status(conn, finding_id, FindingStatus.APPROVED)

        application = create_app(conn)
        client = TestClient(application)
        resp = client.post(
            "/github/create-issues",
            data={"dry_run": "true"},
        )
        assert resp.status_code == 200
        assert "dry run" in resp.text.lower()

    def test_github_create_no_config(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        conn, _, finding_id = seeded_db
        update_finding_status(conn, finding_id, FindingStatus.APPROVED)

        application = create_app(conn)
        client = TestClient(application)
        resp = client.post(
            "/github/create-issues",
            data={"dry_run": "false"},
        )
        assert resp.status_code == 200
        assert "not configured" in resp.text.lower()


class TestThemeAndDesign:
    def test_dark_mode_default(self, app: TestClient) -> None:
        resp = app.get("/runs")
        assert 'data-theme="dark"' in resp.text

    def test_google_fonts_loaded(self, app: TestClient) -> None:
        resp = app.get("/runs")
        assert "Bricolage+Grotesque" in resp.text

    def test_app_js_served(self, app: TestClient) -> None:
        resp = app.get("/static/app.js")
        assert resp.status_code == 200

    def test_nav_links(self, app: TestClient) -> None:
        resp = app.get("/runs")
        assert 'href="/github"' in resp.text
        assert 'href="/scan"' in resp.text
        assert "Sentinel" in resp.text
