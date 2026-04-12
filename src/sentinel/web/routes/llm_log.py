"""LLM call log viewer — drill-down into prompts, responses, verdicts."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import Response

from sentinel.web.shared import _get_conn, templates

logger = logging.getLogger(__name__)


async def llm_log_page(request: Request) -> Response:
    """Paginated LLM call log with filters.

    Query params: detector, model, verdict, run_id, page.
    """
    conn = _get_conn(request.app)

    detector = request.query_params.get("detector", "")
    model = request.query_params.get("model", "")
    verdict = request.query_params.get("verdict", "")
    run_id_str = request.query_params.get("run_id", "")
    run_id = int(run_id_str) if run_id_str.isdigit() else None
    page_str = request.query_params.get("page", "1")
    page = max(1, int(page_str)) if page_str.isdigit() else 1
    per_page = 50

    from sentinel.store.llm_log import get_llm_log_entries, get_llm_log_filters

    entries, total = get_llm_log_entries(
        conn,
        detector=detector,
        model=model,
        verdict=verdict,
        run_id=run_id,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    filters = get_llm_log_filters(conn)
    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(request, "llm_log.html", {
        "entries": entries,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filters": filters,
        "filter_detector": detector,
        "filter_model": model,
        "filter_verdict": verdict,
        "filter_run_id": run_id_str,
    })
