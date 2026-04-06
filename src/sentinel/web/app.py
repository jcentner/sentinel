"""Starlette application for the Sentinel web UI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from sentinel.models import Finding, FindingStatus
from sentinel.store.findings import (
    get_finding_by_id,
    get_findings_by_run,
    suppress_finding,
    update_finding_status,
)
from sentinel.store.runs import get_run_by_id, get_run_history

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _get_conn(app: Starlette) -> sqlite3.Connection:
    """Retrieve the shared DB connection from app state."""
    return app.state.db_conn  # type: ignore[no-any-return]


# ── Route handlers ───────────────────────────────────────────────────


async def index(request: Request) -> Response:
    """Redirect to latest run or show empty state."""
    conn = _get_conn(request.app)
    runs = get_run_history(conn, limit=1)
    if runs:
        return RedirectResponse(url=f"/runs/{runs[0].id}", status_code=302)
    return templates.TemplateResponse(request, "index.html", {"runs": []})


async def runs_list(request: Request) -> Response:
    """Show all past runs."""
    conn = _get_conn(request.app)
    runs = get_run_history(conn, limit=100)
    return templates.TemplateResponse(request, "runs.html", {"runs": runs})


async def run_detail(request: Request) -> Response:
    """Show findings for a specific run."""
    conn = _get_conn(request.app)
    run_id = int(request.path_params["run_id"])
    run = get_run_by_id(conn, run_id)
    if run is None:
        return Response("Run not found", status_code=404)

    findings = get_findings_by_run(conn, run_id)

    # Group by severity for display
    grouped: dict[str, list[Finding]] = {"critical": [], "high": [], "medium": [], "low": []}
    for f in findings:
        grouped.setdefault(f.severity.value, []).append(f)

    return templates.TemplateResponse(request, "run_detail.html", {
        "run": run,
        "findings": findings,
        "grouped": grouped,
    })


async def finding_detail(request: Request) -> Response:
    """Show full details of a single finding."""
    conn = _get_conn(request.app)
    finding_id = int(request.path_params["finding_id"])
    finding = get_finding_by_id(conn, finding_id)
    if finding is None:
        return Response("Finding not found", status_code=404)
    return templates.TemplateResponse(request, "finding_detail.html", {
        "finding": finding,
    })


async def finding_action(request: Request) -> Response:
    """Handle approve/suppress actions via POST (htmx-friendly)."""
    conn = _get_conn(request.app)
    finding_id = int(request.path_params["finding_id"])
    finding = get_finding_by_id(conn, finding_id)
    if finding is None:
        return Response("Finding not found", status_code=404)

    form = await request.form()
    action = form.get("action", "")

    if action == "approve":
        update_finding_status(conn, finding_id, FindingStatus.APPROVED)
    elif action == "suppress":
        reason = str(form.get("reason", "")) or None
        suppress_finding(conn, finding.fingerprint, reason=reason)
    else:
        return Response("Unknown action", status_code=400)

    # If htmx request, return just the updated status badge
    if request.headers.get("hx-request"):
        new_status = "approved" if action == "approve" else "suppressed"
        return Response(
            f'<span class="badge badge-{new_status}">{new_status}</span>',
            media_type="text/html",
        )

    # Regular form POST — redirect back
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


# ── App factory ──────────────────────────────────────────────────────


def create_app(db_conn: sqlite3.Connection) -> Starlette:
    """Create the Starlette application with the given DB connection."""
    routes = [
        Route("/", endpoint=index),
        Route("/runs", endpoint=runs_list),
        Route("/runs/{run_id:int}", endpoint=run_detail),
        Route("/findings/{finding_id:int}", endpoint=finding_detail),
        Route("/findings/{finding_id:int}/action", endpoint=finding_action, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ]

    app = Starlette(routes=routes)
    app.state.db_conn = db_conn
    return app
