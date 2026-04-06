"""Starlette application for the Sentinel web UI."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

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
    """Show findings for a specific run, with optional filters."""
    conn = _get_conn(request.app)
    run_id = int(request.path_params["run_id"])
    run = get_run_by_id(conn, run_id)
    if run is None:
        return Response("Run not found", status_code=404)

    findings = get_findings_by_run(conn, run_id)

    # Read filter query params
    filter_severity = request.query_params.get("severity", "")
    filter_status = request.query_params.get("status", "")
    filter_detector = request.query_params.get("detector", "")

    # Collect unique values for filter dropdowns
    all_detectors = sorted({f.detector for f in findings})
    all_statuses = sorted({f.status.value for f in findings})

    # Apply filters
    if filter_severity:
        findings = [f for f in findings if f.severity.value == filter_severity]
    if filter_status:
        findings = [f for f in findings if f.status.value == filter_status]
    if filter_detector:
        findings = [f for f in findings if f.detector == filter_detector]

    # Group by severity for display
    grouped: dict[str, list[Finding]] = {"critical": [], "high": [], "medium": [], "low": []}
    for f in findings:
        grouped.setdefault(f.severity.value, []).append(f)

    return templates.TemplateResponse(request, "run_detail.html", {
        "run": run,
        "findings": findings,
        "grouped": grouped,
        "filter_severity": filter_severity,
        "filter_status": filter_status,
        "filter_detector": filter_detector,
        "all_detectors": all_detectors,
        "all_statuses": all_statuses,
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


async def scan_trigger(request: Request) -> Response:
    """Trigger a new scan via POST."""
    from sentinel.core.runner import run_scan

    conn = _get_conn(request.app)
    repo_path: str | None = getattr(request.app.state, "repo_path", None)
    if not repo_path:
        return Response("No repo configured", status_code=500)

    try:
        run_summary, _findings, _report_path = run_scan(repo_path, conn)
    except Exception:
        logger.exception("Scan failed")
        return Response("Scan failed — check server logs", status_code=500)

    # Redirect to the new run
    if request.headers.get("hx-request"):
        return Response(
            f'<a href="/runs/{run_summary.id}">Scan complete — view run #{run_summary.id}</a>',
            media_type="text/html",
        )
    return RedirectResponse(url=f"/runs/{run_summary.id}", status_code=303)


# ── App factory ──────────────────────────────────────────────────────


def create_app(
    db_conn: sqlite3.Connection, repo_path: str | None = None
) -> Starlette:
    """Create the Starlette application with the given DB connection."""
    routes = [
        Route("/", endpoint=index),
        Route("/runs", endpoint=runs_list),
        Route("/runs/{run_id:int}", endpoint=run_detail),
        Route("/findings/{finding_id:int}", endpoint=finding_detail),
        Route("/findings/{finding_id:int}/action", endpoint=finding_action, methods=["POST"]),
        Route("/scan", endpoint=scan_trigger, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ]

    app = Starlette(routes=routes)
    app.state.db_conn = db_conn
    app.state.repo_path = repo_path
    return app
