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

    # Cluster findings within each severity group by parent directory
    from sentinel.core.clustering import FindingCluster, cluster_findings
    clustered: dict[str, list[Finding | FindingCluster]] = {}
    for sev, sev_findings in grouped.items():
        clustered[sev] = cluster_findings(sev_findings)

    return templates.TemplateResponse(request, "run_detail.html", {
        "run": run,
        "findings": findings,
        "grouped": grouped,
        "clustered": clustered,
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


async def bulk_action(request: Request) -> Response:
    """Handle bulk approve/suppress for multiple findings."""
    conn = _get_conn(request.app)
    run_id = int(request.path_params["run_id"])

    form = await request.form()
    action = str(form.get("action", ""))
    finding_ids_raw = form.getlist("finding_ids")

    if action not in ("approve", "suppress"):
        return Response("Unknown action", status_code=400)
    if not finding_ids_raw:
        return Response("No findings selected", status_code=400)

    # Parse and validate finding IDs
    finding_ids: list[int] = []
    for raw_id in finding_ids_raw:
        try:
            finding_ids.append(int(str(raw_id)))
        except (ValueError, TypeError):
            return Response(f"Invalid finding ID: {raw_id}", status_code=400)

    count = 0
    for fid in finding_ids:
        finding = get_finding_by_id(conn, fid)
        if finding is None:
            continue
        if action == "approve":
            update_finding_status(conn, fid, FindingStatus.APPROVED)
            count += 1
        elif action == "suppress":
            if finding.fingerprint:
                reason = str(form.get("reason", "")) or None
                suppress_finding(conn, finding.fingerprint, reason=reason)
                count += 1

    if request.headers.get("hx-request"):
        past = "approved" if action == "approve" else "suppressed"
        return Response(
            f'<div class="toast toast-success">{count} finding{"s" if count != 1 else ""} {past}</div>',
            headers={"HX-Trigger": "bulkActionComplete"},
            media_type="text/html",
        )
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


async def settings_page(request: Request) -> Response:
    """Display current configuration."""
    import dataclasses
    import os
    from pathlib import Path as _Path

    from sentinel.config import SentinelConfig, load_config

    repo_path = getattr(request.app.state, "repo_path", None) or ""
    if repo_path:
        config = load_config(_Path(repo_path))
        config_file = _Path(repo_path) / "sentinel.toml"
        has_config_file = config_file.exists()
    else:
        config = SentinelConfig()
        has_config_file = False

    fields = [
        {"name": f.name, "value": getattr(config, f.name), "type": f.type}
        for f in dataclasses.fields(config)
    ]

    env_vars = {
        v: bool(os.environ.get(v))
        for v in ["SENTINEL_GITHUB_OWNER", "SENTINEL_GITHUB_REPO", "SENTINEL_GITHUB_TOKEN"]
    }

    return templates.TemplateResponse(request, "settings.html", {
        "fields": fields,
        "repo_path": repo_path,
        "has_config_file": has_config_file,
        "env_vars": env_vars,
    })


async def eval_page(request: Request) -> Response:
    """Show eval form (GET) or run evaluation (POST)."""
    if request.method == "GET":
        current_repo = getattr(request.app.state, "repo_path", "") or ""
        return templates.TemplateResponse(request, "eval.html", {
            "current_repo": current_repo,
            "result": None,
        })

    # POST — run evaluation
    import anyio

    from sentinel.config import load_config
    from sentinel.core.eval import EvalResult, evaluate, load_ground_truth
    from sentinel.core.runner import run_scan
    from sentinel.store.db import get_connection as get_conn

    form = await request.form()
    form_repo = str(form.get("repo_path", "")).strip()
    user_provided = bool(form_repo)
    repo_path: str = form_repo or str(getattr(request.app.state, "repo_path", None) or "")
    if not repo_path:
        return Response("No repo configured", status_code=500)

    repo = Path(repo_path)
    if user_provided and not repo.is_dir():
        return Response(f"Repository path not found: {repo_path}", status_code=400)

    form_gt = str(form.get("ground_truth", "")).strip()
    gt_path = Path(form_gt) if form_gt else repo / "ground-truth.toml"
    if not gt_path.exists():
        return templates.TemplateResponse(request, "eval.html", {
            "current_repo": repo_path,
            "result": None,
            "error": f"Ground truth file not found: {gt_path}",
        })

    config = load_config(repo)

    def _do_eval() -> tuple[EvalResult, int]:
        gt = load_ground_truth(gt_path)
        mem_conn = get_conn(":memory:")
        try:
            _, findings, _ = run_scan(
                str(repo),
                mem_conn,
                model=config.model,
                ollama_url=config.ollama_url,
                skip_judge=True,
                output_path="/dev/null",
            )
        finally:
            mem_conn.close()
        result = evaluate(findings, gt)

        # Persist eval result to the app's DB
        from sentinel.store.eval_store import save_eval_result
        app_conn = _get_conn(request.app)
        save_eval_result(
            app_conn,
            repo_path=str(repo),
            total_findings=result.total_findings,
            true_positives=result.true_positives,
            false_positives_found=result.false_positives_found,
            missing_count=len(result.missing),
            precision=result.precision,
            recall=result.recall,
            ground_truth_path=str(gt_path),
            details={
                "missing": result.missing,
                "unexpected_fps": result.unexpected_fps,
            },
        )

        return result, len(findings)

    try:
        eval_result, total_raw = await anyio.to_thread.run_sync(_do_eval)
    except Exception:
        logger.exception("Evaluation failed")
        return Response("Evaluation failed — check server logs", status_code=500)

    passed = eval_result.precision >= 0.7 and eval_result.recall >= 0.9

    return templates.TemplateResponse(request, "eval.html", {
        "current_repo": repo_path,
        "result": eval_result,
        "total_raw": total_raw,
        "passed": passed,
        "error": None,
    })


async def eval_history_page(request: Request) -> Response:
    """Show eval results history with precision/recall trends."""
    from sentinel.store.eval_store import get_eval_history

    conn = _get_conn(request.app)
    results = get_eval_history(conn, limit=50)
    return templates.TemplateResponse(request, "eval_history.html", {
        "results": results,
    })


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
        Route("/runs/{run_id:int}/bulk-action", endpoint=bulk_action, methods=["POST"]),
        Route("/settings", endpoint=settings_page),
        Route("/eval", endpoint=eval_page, methods=["GET", "POST"]),
        Route("/eval/history", endpoint=eval_history_page),
        Route("/scan", endpoint=scan_page, methods=["GET", "POST"]),
        Route("/github", endpoint=github_page),
        Route("/github/create-issues", endpoint=github_create_issues, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ]

    app = Starlette(routes=routes)
    app.state.db_conn = db_conn
    app.state.repo_path = repo_path
    return app
