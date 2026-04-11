"""Doctor health check route."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import Response

from sentinel.web.shared import templates

logger = logging.getLogger(__name__)


async def doctor_page(request: Request) -> Response:
    """System health check page — web equivalent of ``sentinel doctor``."""
    import anyio

    from sentinel.core.doctor import run_doctor_checks

    repo_path = getattr(request.app.state, "repo_path", None) or ""

    def _run_checks():
        return run_doctor_checks(repo_path or None)

    try:
        results = await anyio.to_thread.run_sync(_run_checks)
    except Exception:
        logger.exception("Doctor check failed")
        return Response("Health check failed — check server logs", status_code=500)

    ok_count = sum(1 for r in results if r.status == "ok")

    return templates.TemplateResponse(request, "doctor.html", {
        "results": results,
        "ok_count": ok_count,
        "total_count": len(results),
        "repo_path": repo_path,
    })
