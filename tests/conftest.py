"""Shared test fixtures for Sentinel tests."""

from __future__ import annotations

import pytest

from sentinel.store.db import get_connection


@pytest.fixture
def db_conn(tmp_path):
    """Provide a fresh SQLite database connection for testing."""
    conn = get_connection(tmp_path / "test.db")
    yield conn
    conn.close()
