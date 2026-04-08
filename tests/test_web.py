"""Tests for the Sentinel web UI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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

    def test_directory_clustering(self, db_conn: sqlite3.Connection) -> None:
        """Run detail should group 3+ findings in the same directory into a cluster."""
        run = create_run(db_conn, "/tmp/test-repo")
        # Create 3 findings in the same directory — should cluster
        for i in range(3):
            insert_finding(db_conn, run.id, Finding(
                detector="todo-scanner",
                category="todo-fixme",
                severity=Severity.MEDIUM,
                confidence=1.0,
                title=f"TODO in file{i}.py",
                description=f"Unresolved TODO #{i}",
                evidence=[],
                file_path=f"src/utils/file{i}.py",
                fingerprint=f"cluster-fp-{i}",
            ))
        # 1 standalone finding
        insert_finding(db_conn, run.id, Finding(
            detector="lint-runner",
            category="code-quality",
            severity=Severity.MEDIUM,
            confidence=1.0,
            title="Unused variable",
            description="Unused var",
            evidence=[],
            file_path="other/standalone.py",
            fingerprint="standalone-fp",
        ))
        complete_run(db_conn, run.id, 4)
        client = TestClient(create_app(db_conn))
        resp = client.get(f"/runs/{run.id}")
        assert resp.status_code == 200
        # Cluster should appear with the directory name
        assert "src/utils" in resp.text
        assert "finding-cluster" in resp.text
        # Standalone finding should also appear
        assert "Unused variable" in resp.text

    def test_pattern_clustering(self, db_conn: sqlite3.Connection) -> None:
        """Findings with the same detector + normalized title should group by pattern."""
        run = create_run(db_conn, "/tmp/test-repo")
        # 3 findings with same detector + similar title but different directories
        for i, dir_name in enumerate(["src/auth", "src/api", "src/core"]):
            insert_finding(db_conn, run.id, Finding(
                detector="lint-runner",
                category="code-quality",
                severity=Severity.MEDIUM,
                confidence=1.0,
                title=f"Unused import in {dir_name}/handler.py",
                description=f"Unused import #{i}",
                evidence=[],
                file_path=f"{dir_name}/handler.py",
                fingerprint=f"pattern-fp-{i}",
            ))
        complete_run(db_conn, run.id, 3)
        client = TestClient(create_app(db_conn))
        resp = client.get(f"/runs/{run.id}")
        assert resp.status_code == 200
        # Pattern cluster should appear
        assert "finding-cluster" in resp.text


class TestRunCompare:
    def test_compare_not_found(self, app: TestClient) -> None:
        resp = app.get("/runs/9999/compare/9998")
        assert resp.status_code == 404

    def test_compare_runs(self, db_conn: sqlite3.Connection) -> None:
        """Compare two runs showing new, resolved, and persistent findings."""
        # Create two runs
        run1 = create_run(db_conn, "/tmp/test-repo")
        run2 = create_run(db_conn, "/tmp/test-repo")

        # Run 1: findings A, B
        insert_finding(db_conn, run1.id, Finding(
            detector="todo-scanner", category="todo-fixme",
            severity=Severity.MEDIUM, confidence=1.0,
            title="TODO: fix this", description="Unresolved TODO",
            evidence=[], file_path="main.py", fingerprint="fp-a",
        ))
        insert_finding(db_conn, run1.id, Finding(
            detector="lint-runner", category="code-quality",
            severity=Severity.HIGH, confidence=1.0,
            title="Unused import", description="Unused import os",
            evidence=[], file_path="main.py", fingerprint="fp-b",
        ))

        # Run 2: findings B, C (A resolved, C new, B persistent)
        insert_finding(db_conn, run2.id, Finding(
            detector="lint-runner", category="code-quality",
            severity=Severity.HIGH, confidence=1.0,
            title="Unused import", description="Unused import os",
            evidence=[], file_path="main.py", fingerprint="fp-b",
        ))
        insert_finding(db_conn, run2.id, Finding(
            detector="dep-audit", category="dependency",
            severity=Severity.HIGH, confidence=1.0,
            title="Vulnerable package", description="CVE-2024-1234",
            evidence=[], file_path="requirements.txt", fingerprint="fp-c",
        ))

        client = TestClient(create_app(db_conn))
        resp = client.get(f"/runs/{run2.id}/compare/{run1.id}")
        assert resp.status_code == 200
        assert "Run Comparison" in resp.text
        # New finding (C)
        assert "Vulnerable package" in resp.text
        assert "New Findings" in resp.text
        # Resolved finding (A)
        assert "TODO: fix this" in resp.text
        assert "Resolved" in resp.text
        # Persistent finding (B)
        assert "Persistent" in resp.text

    def test_compare_dropdown_on_run_detail(self, db_conn: sqlite3.Connection) -> None:
        """Run detail page shows a 'Compare with' dropdown when multiple runs exist."""
        run1 = create_run(db_conn, "/tmp/test-repo")
        run2 = create_run(db_conn, "/tmp/test-repo")
        insert_finding(db_conn, run1.id, Finding(
            detector="todo-scanner", category="todo-fixme",
            severity=Severity.MEDIUM, confidence=1.0,
            title="TODO: test", description="Test",
            evidence=[], file_path="main.py", fingerprint="fp-dropdown",
        ))
        client = TestClient(create_app(db_conn))
        resp = client.get(f"/runs/{run1.id}")
        assert resp.status_code == 200
        assert "Compare with" in resp.text
        assert f"Run #{run2.id}" in resp.text


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


class TestBulkActions:
    def test_bulk_approve(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, finding_id = seeded_app
        # Get findings to know both IDs
        resp = client.get(f"/runs/{run_id}")
        # Use both finding IDs (seeded_db creates 2)
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "approve", "finding_ids": [str(finding_id), str(finding_id + 1)]},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_bulk_approve_htmx(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, finding_id = seeded_app
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "approve", "finding_ids": [str(finding_id)]},
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "1 finding approved" in resp.text

    def test_bulk_suppress(self, seeded_app: tuple[TestClient, int, int]) -> None:
        client, run_id, finding_id = seeded_app
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "suppress", "finding_ids": [str(finding_id)]},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_bulk_suppress_with_reason(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, run_id, finding_id = seeded_app
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={
                "action": "suppress",
                "finding_ids": [str(finding_id)],
                "reason": "false positive",
            },
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "suppressed" in resp.text

    def test_bulk_no_findings_selected(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, run_id, _ = seeded_app
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "approve"},
        )
        assert resp.status_code == 400
        assert "No findings selected" in resp.text

    def test_bulk_unknown_action(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, run_id, finding_id = seeded_app
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "bogus", "finding_ids": [str(finding_id)]},
        )
        assert resp.status_code == 400

    def test_bulk_invalid_finding_id(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, run_id, _ = seeded_app
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "approve", "finding_ids": ["not-a-number"]},
        )
        assert resp.status_code == 400
        assert "Invalid finding ID" in resp.text

    def test_bulk_updates_db(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        conn, run_id, finding_id = seeded_db
        application = create_app(conn)
        client = TestClient(application)
        client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "approve", "finding_ids": [str(finding_id), str(finding_id + 1)]},
            follow_redirects=False,
        )
        f1 = get_finding_by_id(conn, finding_id)
        f2 = get_finding_by_id(conn, finding_id + 1)
        assert f1 is not None and f1.status == FindingStatus.APPROVED
        assert f2 is not None and f2.status == FindingStatus.APPROVED

    def test_bulk_skips_nonexistent_findings(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, run_id, finding_id = seeded_app
        resp = client.post(
            f"/runs/{run_id}/bulk-action",
            data={"action": "approve", "finding_ids": [str(finding_id), "9999"]},
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "1 finding approved" in resp.text

    def test_run_detail_has_checkboxes(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, run_id, _ = seeded_app
        resp = client.get(f"/runs/{run_id}")
        assert resp.status_code == 200
        assert 'class="bulk-checkbox' in resp.text
        assert 'id="bulk-bar"' in resp.text


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
        monkeypatch.setattr("sentinel.core.provider.create_provider", MagicMock(return_value=MagicMock()))

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
        monkeypatch.setattr("sentinel.core.provider.create_provider", MagicMock(return_value=MagicMock()))

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
        monkeypatch.setattr("sentinel.core.provider.create_provider", MagicMock(return_value=MagicMock()))

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

    def test_protocol_relative_redirect_blocked(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        """Protocol-relative referer (//evil.com) should redirect to /."""
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/action",
            data={"action": "approve"},
            headers={"referer": "//evil.example.com/steal"},
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
        assert 'href="/settings"' in resp.text
        assert 'href="/eval"' in resp.text
        assert "Sentinel" in resp.text


class TestSettingsPage:
    def test_settings_no_repo(self, app: TestClient) -> None:
        resp = app.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text
        assert "Using defaults" in resp.text

    def test_settings_with_repo(
        self, seeded_db: tuple[sqlite3.Connection, int, int], tmp_path: Path
    ) -> None:
        conn, _, _ = seeded_db
        application = create_app(conn, repo_path=str(tmp_path))
        client = TestClient(application)
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "model" in resp.text
        assert "qwen3.5:4b" in resp.text

    def test_settings_with_config_file(
        self, seeded_db: tuple[sqlite3.Connection, int, int], tmp_path: Path
    ) -> None:
        (tmp_path / "sentinel.toml").write_text('[sentinel]\nmodel = "custom-model"\n')
        conn, _, _ = seeded_db
        application = create_app(conn, repo_path=str(tmp_path))
        client = TestClient(application)
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "sentinel.toml found" in resp.text
        assert "custom-model" in resp.text

    def test_settings_shows_env_vars(self, app: TestClient) -> None:
        resp = app.get("/settings")
        assert "SENTINEL_GITHUB_OWNER" in resp.text
        assert "SENTINEL_GITHUB_REPO" in resp.text
        assert "SENTINEL_GITHUB_TOKEN" in resp.text

    def test_settings_shows_all_fields(self, app: TestClient) -> None:
        resp = app.get("/settings")
        for field_name in ["model", "ollama_url", "db_path", "output_dir", "skip_judge",
                           "embed_model", "embed_chunk_size", "embed_chunk_overlap", "detectors_dir"]:
            assert field_name in resp.text


class TestEvalPage:
    def test_eval_form_get(self, app: TestClient) -> None:
        resp = app.get("/eval")
        assert resp.status_code == 200
        assert "Evaluation" in resp.text
        assert "Run Evaluation" in resp.text

    def test_eval_no_repo(self, app: TestClient) -> None:
        resp = app.post("/eval", data={})
        assert resp.status_code == 500
        assert "No repo configured" in resp.text

    def test_eval_missing_ground_truth(
        self, seeded_db: tuple[sqlite3.Connection, int, int], tmp_path: Path
    ) -> None:
        conn, _, _ = seeded_db
        application = create_app(conn, repo_path=str(tmp_path))
        client = TestClient(application)
        resp = client.post("/eval", data={"repo_path": str(tmp_path)})
        assert resp.status_code == 200
        assert "not found" in resp.text

    def test_eval_bad_repo_path(self, app: TestClient) -> None:
        resp = app.post("/eval", data={"repo_path": "/nonexistent/path"})
        assert resp.status_code == 400
        assert "not found" in resp.text

    def test_eval_success(
        self, seeded_db: tuple[sqlite3.Connection, int, int],
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        from unittest.mock import MagicMock

        from sentinel.core.eval import EvalResult

        conn, _, _ = seeded_db
        application = create_app(conn, repo_path=str(tmp_path))
        client = TestClient(application)

        mock_result = EvalResult(
            total_findings=10,
            true_positives=8,
            false_positives_found=1,
            missing=[],
            unexpected_fps=["some FP"],
        )
        monkeypatch.setattr(
            "sentinel.core.runner.run_scan",
            MagicMock(return_value=(MagicMock(), [], "/dev/null")),
        )
        monkeypatch.setattr(
            "sentinel.core.eval.evaluate",
            MagicMock(return_value=mock_result),
        )
        monkeypatch.setattr(
            "sentinel.core.eval.load_ground_truth",
            MagicMock(return_value={}),
        )
        monkeypatch.setattr(
            "sentinel.config.load_config",
            MagicMock(return_value=MagicMock(
                model="test", ollama_url="http://localhost:11434", skip_judge=True
            )),
        )
        monkeypatch.setattr("sentinel.core.provider.create_provider", MagicMock(return_value=MagicMock()))
        # Create a fake ground truth file in the repo
        gt_file = tmp_path / "ground-truth.toml"
        gt_file.write_text("[sentinel]\n")

        # POST without explicit repo_path — uses the app state's repo_path
        resp = client.post("/eval", data={})
        assert resp.status_code == 200
        assert "80%" in resp.text  # precision = 8/10
        assert "PASS" in resp.text or "FAIL" in resp.text


class TestEvalHistoryPage:
    def test_eval_history_empty(self, app: TestClient) -> None:
        resp = app.get("/eval/history")
        assert resp.status_code == 200
        assert "No evaluation results" in resp.text

    def test_eval_history_with_data(self, db_conn: sqlite3.Connection) -> None:
        from sentinel.store.eval_store import save_eval_result
        save_eval_result(db_conn, "/tmp/repo", 15, 15, 0, 0, 1.0, 1.0)
        save_eval_result(db_conn, "/tmp/repo", 12, 10, 1, 2, 0.833, 0.833)
        client = TestClient(create_app(db_conn))
        resp = client.get("/eval/history")
        assert resp.status_code == 200
        assert "Evaluation History" in resp.text
        assert "100%" in resp.text
        assert "83%" in resp.text
        assert "PASS" in resp.text

    def test_eval_history_chart_with_multiple_results(self, db_conn: sqlite3.Connection) -> None:
        """Chart SVG renders when there are 2+ eval results."""
        import re

        from sentinel.store.eval_store import save_eval_result
        save_eval_result(db_conn, "/tmp/repo", 15, 15, 0, 0, 1.0, 1.0)
        save_eval_result(db_conn, "/tmp/repo", 12, 10, 1, 2, 0.833, 0.833)
        client = TestClient(create_app(db_conn))
        resp = client.get("/eval/history")
        assert resp.status_code == 200
        assert "eval-chart-svg" in resp.text
        assert "chart-line-precision" in resp.text
        assert "chart-line-recall" in resp.text
        assert "Precision" in resp.text and "Recall Trend" in resp.text
        # Verify polyline contains valid numeric coordinates
        assert re.search(r'points="\s*[\d.]+,[\d.]+ [\d.]+,[\d.]+"', resp.text)

    def test_eval_history_no_chart_single_result(self, db_conn: sqlite3.Connection) -> None:
        """No chart when only 1 eval result exists."""
        from sentinel.store.eval_store import save_eval_result
        save_eval_result(db_conn, "/tmp/repo", 15, 15, 0, 0, 1.0, 1.0)
        client = TestClient(create_app(db_conn))
        resp = client.get("/eval/history")
        assert resp.status_code == 200
        assert "eval-chart-svg" not in resp.text


# ── Annotation tests ─────────────────────────────────────────────────


class TestAnnotations:
    def test_finding_detail_shows_notes_section(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, _, finding_id = seeded_app
        resp = client.get(f"/findings/{finding_id}")
        assert resp.status_code == 200
        assert "Notes" in resp.text
        assert "Add a note" in resp.text

    def test_add_annotation(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/annotations",
            data={"content": "This is a test note"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Check the note appears on the finding detail page
        detail = client.get(f"/findings/{finding_id}")
        assert "This is a test note" in detail.text

    def test_add_annotation_htmx(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/annotations",
            data={"content": "An htmx note"},
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "An htmx note" in resp.text

    def test_add_annotation_empty_content(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        client, _, finding_id = seeded_app
        resp = client.post(
            f"/findings/{finding_id}/annotations",
            data={"content": "   "},
        )
        assert resp.status_code == 400

    def test_add_annotation_not_found(self, app: TestClient) -> None:
        resp = app.post(
            "/findings/9999/annotations",
            data={"content": "note"},
        )
        assert resp.status_code == 404

    def test_delete_annotation(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        from sentinel.store.findings import add_annotation

        conn, _, finding_id = seeded_db
        aid = add_annotation(conn, finding_id, "Delete me")
        client = TestClient(create_app(conn))

        resp = client.post(
            f"/findings/{finding_id}/annotations/{aid}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303

        detail = client.get(f"/findings/{finding_id}")
        assert "Delete me" not in detail.text

    def test_delete_annotation_htmx(
        self, seeded_db: tuple[sqlite3.Connection, int, int]
    ) -> None:
        from sentinel.store.findings import add_annotation

        conn, _, finding_id = seeded_db
        add_annotation(conn, finding_id, "Keep this")
        aid2 = add_annotation(conn, finding_id, "Delete this")
        client = TestClient(create_app(conn))

        resp = client.post(
            f"/findings/{finding_id}/annotations/{aid2}/delete",
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "Keep this" in resp.text
        assert "Delete this" not in resp.text

    def test_annotation_xss_escaped(
        self, seeded_app: tuple[TestClient, int, int]
    ) -> None:
        """HTML in annotation content is escaped in both template and htmx paths."""
        client, _, finding_id = seeded_app
        xss_payload = '<script>alert("xss")</script>'

        # htmx path
        resp = client.post(
            f"/findings/{finding_id}/annotations",
            data={"content": xss_payload},
            headers={"hx-request": "true"},
        )
        assert resp.status_code == 200
        assert "<script>" not in resp.text
        assert "&lt;script&gt;" in resp.text

        # Template path (finding detail page)
        detail = client.get(f"/findings/{finding_id}")
        assert "<script>alert" not in detail.text
        assert "&lt;script&gt;" in detail.text
