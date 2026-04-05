"""Tests for GitHub issue creation module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sentinel.github import (
    GitHubConfig,
    _format_issue,
    _issue_labels,
    create_issues,
    get_approved_findings,
    get_github_config,
)
from sentinel.models import (
    Evidence,
    EvidenceType,
    Finding,
    FindingStatus,
    Severity,
)
from sentinel.store.db import get_connection
from sentinel.store.findings import insert_finding, update_finding_status
from sentinel.store.runs import create_run


@pytest.fixture
def db_conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = get_connection(Path(tmpdir) / "test.db")
        yield conn
        conn.close()


def _sample_finding(fingerprint: str = "fp-001", title: str = "Test finding") -> Finding:
    return Finding(
        detector="test-detector",
        category="code-quality",
        severity=Severity.MEDIUM,
        confidence=0.8,
        title=title,
        description="Something is wrong",
        evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="bad code")],
        file_path="src/x.py",
        line_start=10,
        fingerprint=fingerprint,
    )


class TestGitHubConfig:
    def test_from_explicit_args(self):
        cfg = get_github_config(owner="me", repo="proj", token="tok123")
        assert cfg is not None
        assert cfg.owner == "me"
        assert cfg.repo == "proj"
        assert cfg.token == "tok123"

    def test_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_GITHUB_OWNER", "envowner")
        monkeypatch.setenv("SENTINEL_GITHUB_REPO", "envrepo")
        monkeypatch.setenv("SENTINEL_GITHUB_TOKEN", "envtoken")
        cfg = get_github_config()
        assert cfg is not None
        assert cfg.owner == "envowner"
        assert cfg.repo == "envrepo"
        assert cfg.token == "envtoken"

    def test_returns_none_if_missing(self):
        cfg = get_github_config()
        assert cfg is None

    def test_args_override_env(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_GITHUB_OWNER", "envowner")
        monkeypatch.setenv("SENTINEL_GITHUB_REPO", "envrepo")
        monkeypatch.setenv("SENTINEL_GITHUB_TOKEN", "envtoken")
        cfg = get_github_config(owner="override")
        assert cfg.owner == "override"
        assert cfg.repo == "envrepo"


class TestFormatIssue:
    def test_basic_format(self):
        finding = _sample_finding()
        title, body = _format_issue(finding)
        assert title == "[Sentinel] Test finding"
        assert "test-detector" in body
        assert "code-quality" in body
        assert "medium" in body
        assert "80%" in body
        assert "src/x.py" in body

    def test_fingerprint_marker_in_body(self):
        finding = _sample_finding(fingerprint="abc123")
        _, body = _format_issue(finding)
        assert "<!-- sentinel:fingerprint:abc123 -->" in body

    def test_evidence_included(self):
        finding = _sample_finding()
        _, body = _format_issue(finding)
        assert "Evidence" in body
        assert "bad code" in body

    def test_line_range_in_location(self):
        finding = _sample_finding()
        finding.line_end = 20
        _, body = _format_issue(finding)
        assert "src/x.py#L10-L20" in body


class TestIssueLabels:
    def test_default_labels(self):
        finding = _sample_finding()
        labels = _issue_labels(finding)
        assert "sentinel" in labels
        assert "severity:medium" in labels


class TestGetApprovedFindings:
    def test_returns_approved_only(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        fid1 = insert_finding(db_conn, run.id, _sample_finding("fp-A", "Finding A"))
        insert_finding(db_conn, run.id, _sample_finding("fp-B", "Finding B"))
        update_finding_status(db_conn, fid1, FindingStatus.APPROVED)
        # fid2 remains NEW

        approved = get_approved_findings(db_conn)
        assert len(approved) == 1
        assert approved[0][0] == fid1
        assert approved[0][1].title == "Finding A"

    def test_empty_when_none_approved(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        insert_finding(db_conn, run.id, _sample_finding())
        assert get_approved_findings(db_conn) == []


class TestCreateIssues:
    def test_dry_run(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        fid = insert_finding(db_conn, run.id, _sample_finding())
        update_finding_status(db_conn, fid, FindingStatus.APPROVED)

        gh = GitHubConfig(owner="test", repo="proj", token="fake")
        results = create_issues(db_conn, gh, dry_run=True)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].error == "dry run"

    def test_skips_existing_fingerprints(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        fid = insert_finding(db_conn, run.id, _sample_finding("fp-exists"))
        update_finding_status(db_conn, fid, FindingStatus.APPROVED)

        gh = GitHubConfig(owner="test", repo="proj", token="fake")

        with patch("sentinel.github._get_existing_issue_fingerprints") as mock_existing:
            mock_existing.return_value = {
                "fp-exists": "https://github.com/test/proj/issues/1"
            }
            results = create_issues(db_conn, gh)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].issue_url == "https://github.com/test/proj/issues/1"
        assert results[0].error == "Issue already exists"

    def test_successful_creation(self, db_conn):
        run = create_run(db_conn, "/tmp/repo")
        fid = insert_finding(db_conn, run.id, _sample_finding("fp-new"))
        update_finding_status(db_conn, fid, FindingStatus.APPROVED)

        gh = GitHubConfig(owner="test", repo="proj", token="fake")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "html_url": "https://github.com/test/proj/issues/42"
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("sentinel.github._get_existing_issue_fingerprints", return_value={}),
            patch("httpx.post", return_value=mock_resp),
        ):
            results = create_issues(db_conn, gh)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].issue_url == "https://github.com/test/proj/issues/42"

    def test_no_approved_returns_empty(self, db_conn):
        gh = GitHubConfig(owner="test", repo="proj", token="fake")
        results = create_issues(db_conn, gh)
        assert results == []
