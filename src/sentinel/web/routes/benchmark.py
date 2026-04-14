"""Benchmark form and results routes."""

from __future__ import annotations

import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

from sentinel.web.shared import templates

logger = logging.getLogger(__name__)


async def benchmark_page(request: Request) -> Response:
    """Show benchmark form (GET) or run benchmark (POST)."""
    if request.method == "GET":
        current_repo = getattr(request.app.state, "repo_path", "") or ""
        return templates.TemplateResponse(request, "benchmark.html", {
            "current_repo": current_repo,
            "result": None,
        })

    # POST — run benchmark
    import anyio

    from sentinel.config import load_config
    from sentinel.core.benchmark import BenchmarkResult, run_benchmark, save_benchmark

    form = await request.form()
    repo_path_str = str(form.get("repo_path", "")).strip()
    user_provided = bool(repo_path_str)
    repo_path: str = repo_path_str or str(
        getattr(request.app.state, "repo_path", None) or ""
    )
    if not repo_path:
        return Response("No repo configured", status_code=500)

    repo = Path(repo_path)
    if user_provided and not repo.is_dir():
        return Response(f"Repository path not found: {repo_path}", status_code=400)

    skip_judge = str(form.get("skip_judge", "")) == "on"
    skip_llm = str(form.get("skip_llm", "")) == "on"
    gt_field = str(form.get("ground_truth", "")).strip()
    gt_path = gt_field if gt_field else None
    save = str(form.get("save_results", "")) == "on"

    config = load_config(repo)
    model_name = config.model
    provider_name = config.provider

    def _do_benchmark() -> tuple[BenchmarkResult, str | None]:
        from sentinel.core.provider import create_provider

        provider = create_provider(config)
        result = run_benchmark(
            str(repo),
            provider=provider,
            skip_judge=skip_judge,
            skip_llm=skip_llm,
            model=model_name,
            provider_name=provider_name,
            model_capability=config.model_capability or "basic",
            ground_truth_path=gt_path,
        )
        saved_path: str | None = None
        if save:
            saved_path = save_benchmark(result, "benchmarks")
        return result, saved_path

    try:
        result, saved_path = await anyio.to_thread.run_sync(_do_benchmark)
    except Exception:
        logger.exception("Benchmark failed")
        return templates.TemplateResponse(request, "benchmark.html", {
            "current_repo": repo_path,
            "result": None,
            "error": "Benchmark failed — check server logs",
        })

    return templates.TemplateResponse(request, "benchmark.html", {
        "current_repo": repo_path,
        "result": result,
        "saved_path": saved_path,
        "error": None,
    })
