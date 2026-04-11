"""Evaluation form, trigger, and history routes."""

from __future__ import annotations

import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

from sentinel.web.shared import _get_conn, templates

logger = logging.getLogger(__name__)


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
            from sentinel.core.provider import create_provider

            provider = create_provider(config)
            _, findings, _ = run_scan(
                str(repo),
                mem_conn,
                provider=provider,
                skip_judge=True,
                output_path="/dev/null",
            )
        finally:
            mem_conn.close()
        result = evaluate(findings, gt)

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

    chart_points: list[dict[str, str | float]] = []
    if len(results) >= 2:
        chronological = list(reversed(results))
        for r in chronological:
            chart_points.append({
                "precision": round(r.precision * 100, 1),
                "recall": round(r.recall * 100, 1),
                "label": r.evaluated_at.strftime("%m/%d") if r.evaluated_at else "?",
            })

    return templates.TemplateResponse(request, "eval_history.html", {
        "results": results,
        "chart_points": chart_points,
    })
