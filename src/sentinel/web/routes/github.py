"""GitHub issues dashboard and creation routes."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import Response

from sentinel.web.shared import _get_conn, templates

logger = logging.getLogger(__name__)


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
