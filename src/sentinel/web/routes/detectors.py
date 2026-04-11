"""Detectors page — compatibility matrix + detector configuration."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from sentinel.web.shared import templates


async def detectors_page(request: Request) -> Response:
    """Model-detector compatibility matrix and detector configuration."""
    from sentinel.core.compatibility import (
        MODEL_CLASSES,
        build_summary_table,
    )

    rows = build_summary_table()
    llm_rows = [r for r in rows if r["tier"] == "llm-assisted"]
    det_rows = [r for r in rows if r["tier"] in ("deterministic", "heuristic")]
    judge_row = next((r for r in rows if r["detector"] == "(judge)"), None)

    return templates.TemplateResponse(request, "compatibility.html", {
        "model_classes": MODEL_CLASSES,
        "llm_rows": llm_rows,
        "det_rows": det_rows,
        "judge_row": judge_row,
    })
