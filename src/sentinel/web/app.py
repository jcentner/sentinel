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

from sentinel.models import Finding, FindingStatus, RunSummary
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
        if not finding.fingerprint:
            return Response("Finding has no fingerprint", status_code=400)
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

    # Regular form POST — redirect back (validate referer is a relative path)
    referer = request.headers.get("referer", "/")
    url = referer if referer.startswith("/") else "/"
    return RedirectResponse(url=url, status_code=303)


async def scan_page(request: Request) -> Response:
    """Show scan form (GET) or trigger a scan (POST)."""
    if request.method == "GET":
        current_repo = getattr(request.app.state, "repo_path", "") or ""
        return templates.TemplateResponse(request, "scan.html", {
            "current_repo": current_repo,
        })

    # POST — trigger scan
    import anyio

    from sentinel.config import load_config
    from sentinel.core.runner import run_scan

    conn = _get_conn(request.app)

    form = await request.form()
    form_repo = str(form.get("repo_path", "")).strip()
    user_provided = bool(form_repo)
    repo_path: str = form_repo or str(getattr(request.app.state, "repo_path", None) or "")
    if not repo_path:
        return Response("No repo configured", status_code=500)

    repo = Path(repo_path)
    # Only validate path existence for user-supplied paths
    if user_provided and not repo.is_dir():
        return Response(f"Repository path not found: {repo_path}", status_code=400)

    config = load_config(repo)

    # Apply form overrides
    form_model = str(form.get("model", "")).strip()
    if form_model:
        config.model = form_model
    form_embed = str(form.get("embed_model", "")).strip()
    if form_embed:
        config.embed_model = form_embed
    if form.get("skip_judge"):
        config.skip_judge = True

    def _do_scan() -> tuple[RunSummary, list[Finding], str]:
        return run_scan(
            str(repo),
            conn,
            model=config.model,
            ollama_url=config.ollama_url,
            skip_judge=config.skip_judge,
            embed_model=config.embed_model,
        )

    try:
        run_summary, _findings, _report_path = await anyio.to_thread.run_sync(_do_scan)
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


async def github_page(request: Request) -> Response:
    """GitHub issues dashboard — view approved findings and create issues."""
    from sentinel.github import get_approved_findings, get_github_config

    conn = _get_conn(request.app)
    approved = get_approved_findings(conn)

    gh = get_github_config()
    gh_configured = gh is not None

    return templates.TemplateResponse(request, "github.html", {
        "approved": approved,
        "gh_configured": gh_configured,
        "gh_owner": gh.owner if gh else "",
        "gh_repo": gh.repo if gh else "",
    })


async def github_create_issues(request: Request) -> Response:
    """Create GitHub issues from approved findings."""
    import anyio

    from sentinel.github import IssueResult, create_issues, get_github_config

    conn = _get_conn(request.app)
    form = await request.form()
    dry_run = str(form.get("dry_run", "false")).lower() == "true"

    gh = get_github_config()
    if gh is None and not dry_run:
        return Response(
            '<div class="toast toast-error">GitHub not configured. '
            "Set SENTINEL_GITHUB_OWNER, SENTINEL_GITHUB_REPO, and SENTINEL_GITHUB_TOKEN env vars.</div>",
            media_type="text/html",
        )

    if dry_run and gh is None:
        # Dry run without GitHub config — show what would be created
        from sentinel.github import get_approved_findings

        approved = get_approved_findings(conn)
        from sentinel.github import IssueResult

        results = [
            IssueResult(
                finding_id=db_id,
                fingerprint=f.fingerprint,
                success=True,
                error="dry run",
            )
            for db_id, f in approved
        ]
        return templates.TemplateResponse(request, "github_results.html", {
            "results": results,
            "dry_run": True,
        })

    assert gh is not None

    def _do_create() -> list[IssueResult]:
        return create_issues(conn, gh, dry_run=dry_run)

    try:
        results = await anyio.to_thread.run_sync(_do_create)
    except Exception:
        logger.exception("Issue creation failed")
        return Response("Issue creation failed — check server logs", status_code=500)

    return templates.TemplateResponse(request, "github_results.html", {
        "results": results,
        "dry_run": dry_run,
    })


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
        Route("/scan", endpoint=scan_page, methods=["GET", "POST"]),
        Route("/github", endpoint=github_page),
        Route("/github/create-issues", endpoint=github_create_issues, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ]

    app = Starlette(routes=routes)
    app.state.db_conn = db_conn
    app.state.repo_path = repo_path
    return app
