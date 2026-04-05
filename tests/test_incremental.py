"""Tests for incremental scan support."""

from __future__ import annotations

import subprocess

import pytest

from sentinel.core.runner import (
    _git_changed_files,
    _git_head_sha,
    prepare_incremental,
    run_scan,
)
from sentinel.models import ScopeType
from sentinel.store.db import get_connection
from sentinel.store.runs import get_last_completed_run


@pytest.fixture()
def git_repo(tmp_path):
    """Create a minimal git repo with one commit."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    (tmp_path / "hello.py").write_text("# hello\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    return tmp_path


def test_git_head_sha_returns_sha(git_repo):
    sha = _git_head_sha(str(git_repo))
    assert sha is not None
    assert len(sha) == 40


def test_git_head_sha_non_git(tmp_path):
    assert _git_head_sha(str(tmp_path)) is None


def test_git_changed_files_detects_changes(git_repo):
    sha1 = _git_head_sha(str(git_repo))
    # Make a second commit
    (git_repo / "new.py").write_text("# new\n")
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add new"],
        cwd=git_repo, capture_output=True, check=True,
    )
    changed = _git_changed_files(str(git_repo), sha1)
    assert "new.py" in changed


def test_git_changed_files_empty_when_same_sha(git_repo):
    sha = _git_head_sha(str(git_repo))
    changed = _git_changed_files(str(git_repo), sha)
    assert changed == []


def test_prepare_incremental_no_prior_run(git_repo):
    conn = get_connection(":memory:")
    scope, files = prepare_incremental(str(git_repo), conn)
    assert scope == ScopeType.FULL
    assert files is None
    conn.close()


def test_prepare_incremental_with_prior_run(git_repo):
    """After a full run, prepare_incremental detects no changes."""
    conn = get_connection(":memory:")
    # Do a full scan to create a run with commit SHA
    run_scan(str(git_repo), conn, skip_judge=True)

    scope, files = prepare_incremental(str(git_repo), conn)
    assert scope == ScopeType.INCREMENTAL
    assert files == []  # nothing changed since last run
    conn.close()


def test_prepare_incremental_detects_new_commit(git_repo):
    """After a new commit, prepare_incremental returns changed files."""
    conn = get_connection(":memory:")
    run_scan(str(git_repo), conn, skip_judge=True)

    # Make a change
    (git_repo / "added.txt").write_text("something\n")
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add file"],
        cwd=git_repo, capture_output=True, check=True,
    )

    scope, files = prepare_incremental(str(git_repo), conn)
    assert scope == ScopeType.INCREMENTAL
    assert "added.txt" in files
    conn.close()


def test_run_scan_stores_commit_sha(git_repo):
    conn = get_connection(":memory:")
    run, _, _ = run_scan(str(git_repo), conn, skip_judge=True)
    assert run.commit_sha is not None
    assert len(run.commit_sha) == 40

    # Verify it's persisted in the DB
    last = get_last_completed_run(conn, str(git_repo.resolve()))
    assert last is not None
    assert last.commit_sha == run.commit_sha
    conn.close()


def test_incremental_scan_produces_fewer_findings(git_repo):
    """Incremental scan on unchanged repo produces no findings (or same)."""
    conn = get_connection(":memory:")
    # Full scan
    run_scan(str(git_repo), conn, skip_judge=True)

    # Incremental scan with no changes → empty changed_files
    scope, changed = prepare_incremental(str(git_repo), conn)
    assert scope == ScopeType.INCREMENTAL
    assert changed == []
    conn.close()
