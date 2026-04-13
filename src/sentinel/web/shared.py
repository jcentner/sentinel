"""Shared helpers for Sentinel web route modules."""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Generator
from pathlib import Path

from starlette.applications import Starlette
from starlette.templating import Jinja2Templates

from sentinel.store.db import get_connection

_TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _format_ts(val: object) -> str:
    """Format a timestamp consistently across all templates."""
    if not val:
        return ""
    if isinstance(val, str):
        return val[:16].replace("T", " ")
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M")  # type: ignore[union-attr]
    return str(val)


templates.env.filters["ts"] = _format_ts


def _get_conn(app: Starlette) -> sqlite3.Connection:
    """Get a DB connection — per-request if db_path is set, shared otherwise.

    When db_path is set (production), opens a fresh connection for thread
    safety (TD-037). Caller must close it or use _open_db().
    When db_conn is set (tests), returns the shared connection as-is.
    """
    db_path: str = getattr(app.state, "db_path", "")
    if db_path:
        return get_connection(db_path, check_same_thread=True)
    return app.state.db_conn  # type: ignore[no-any-return]


@contextlib.contextmanager
def _open_db(app: Starlette) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for a scoped database connection.

    Closes the connection on exit when using per-request mode (db_path).
    No-op close when using shared connection mode (tests).
    """
    db_path: str = getattr(app.state, "db_path", "")
    if db_path:
        conn = get_connection(db_path, check_same_thread=True)
        try:
            yield conn
        finally:
            conn.close()
    else:
        yield app.state.db_conn
