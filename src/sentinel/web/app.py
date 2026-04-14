"""Starlette application factory for the Sentinel web UI.

Route handlers live in sentinel.web.routes.* modules.
Shared helpers (templates, DB access) are in sentinel.web.shared.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from sentinel.store.runs import get_run_history
from sentinel.web.routes.benchmark import benchmark_page
from sentinel.web.routes.detectors import detectors_page
from sentinel.web.routes.doctor import doctor_page
from sentinel.web.routes.eval import eval_history_page, eval_page
from sentinel.web.routes.findings import (
    annotation_add,
    annotation_delete,
    bulk_action,
    finding_action,
    finding_detail,
)
from sentinel.web.routes.github import github_create_issues, github_page
from sentinel.web.routes.index import index_page as embed_index_page
from sentinel.web.routes.llm_log import llm_log_page
from sentinel.web.routes.runs import run_compare, run_detail, runs_list
from sentinel.web.routes.scan import scan_page
from sentinel.web.routes.settings import settings_page
from sentinel.web.shared import _get_conn, templates

_STATIC_DIR = Path(__file__).parent / "static"


# ── Root route ───────────────────────────────────────────────────────


async def index(request: Request) -> Response:
    """Redirect to runs list or show empty state."""
    conn = _get_conn(request.app)
    runs = get_run_history(conn, limit=1)
    if runs:
        return RedirectResponse(url="/runs", status_code=302)
    return templates.TemplateResponse(request, "index.html", {"runs": []})


# ── App factory ──────────────────────────────────────────────────────


def create_app(
    db_conn: sqlite3.Connection | None = None,
    repo_path: str | None = None,
    *,
    db_path: str | None = None,
    allowed_scan_roots: list[str] | None = None,
) -> Starlette:
    """Create the Starlette application.

    Args:
        db_conn: Fixed database connection (for tests). Mutually exclusive
            with db_path.
        repo_path: Default repository path for scans.
        db_path: Path to SQLite database. When set, opens per-request
            connections for thread safety (TD-037). Preferred for production.
        allowed_scan_roots: If set, only directories under these roots
            can be scanned via the web UI (TD-025 path validation).
    """
    from sentinel.web.csrf import CSRFMiddleware

    routes = [
        Route("/", endpoint=index),
        Route("/runs", endpoint=runs_list),
        Route("/runs/{run_id:int}", endpoint=run_detail),
        Route("/runs/{run_id:int}/compare/{base_run_id:int}", endpoint=run_compare),
        Route("/findings/{finding_id:int}", endpoint=finding_detail),
        Route("/findings/{finding_id:int}/action", endpoint=finding_action, methods=["POST"]),
        Route("/findings/{finding_id:int}/annotations", endpoint=annotation_add, methods=["POST"]),
        Route("/findings/{finding_id:int}/annotations/{annotation_id:int}/delete", endpoint=annotation_delete, methods=["POST"]),
        Route("/runs/{run_id:int}/bulk-action", endpoint=bulk_action, methods=["POST"]),
        Route("/settings", endpoint=settings_page, methods=["GET", "POST"]),
        Route("/compatibility", endpoint=detectors_page, methods=["GET", "POST"]),
        Route("/detectors", endpoint=detectors_page, methods=["GET", "POST"]),
        Route("/eval", endpoint=eval_page, methods=["GET", "POST"]),
        Route("/eval/history", endpoint=eval_history_page),
        Route("/benchmark", endpoint=benchmark_page, methods=["GET", "POST"]),
        Route("/scan", endpoint=scan_page, methods=["GET", "POST"]),
        Route("/doctor", endpoint=doctor_page),
        Route("/github", endpoint=github_page),
        Route("/github/create-issues", endpoint=github_create_issues, methods=["POST"]),
        Route("/llm-log", endpoint=llm_log_page),
        Route("/embed-index", endpoint=embed_index_page),
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ]

    app = Starlette(routes=routes)
    app.state.db_conn = db_conn
    app.state.db_path = db_path or ""
    app.state.repo_path = repo_path
    app.state.allowed_scan_roots = allowed_scan_roots

    app.add_middleware(CSRFMiddleware)

    return app
