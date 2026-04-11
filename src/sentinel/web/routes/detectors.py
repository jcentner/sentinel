"""Detectors page — compatibility matrix + detector configuration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from sentinel.web.shared import _get_conn, templates

logger = logging.getLogger(__name__)


async def detectors_page(request: Request) -> Response:
    """Model-detector compatibility matrix and detector configuration.

    GET: Show matrix + current detector config with inline toggles.
    POST: Save detector enable/disable and per-detector model overrides.
    """
    from sentinel.core.compatibility import (
        DETECTOR_INFO,
        MODEL_CLASSES,
        build_summary_table,
    )

    repo_path = getattr(request.app.state, "repo_path", None) or ""

    if request.method == "POST":
        return await _detectors_save(request, repo_path, DETECTOR_INFO)

    # Load current config for toggle state
    config = None
    has_config_file = False
    if repo_path:
        from sentinel.config import load_config

        config = load_config(Path(repo_path))
        has_config_file = (Path(repo_path) / "sentinel.toml").exists()

    rows = build_summary_table()
    llm_rows = [r for r in rows if r["tier"] == "llm-assisted"]
    det_rows = [r for r in rows if r["tier"] in ("deterministic", "heuristic")]
    judge_row = next((r for r in rows if r["detector"] == "(judge)"), None)

    # Build detector state for template
    all_detector_names = sorted(DETECTOR_INFO.keys())
    detector_states: list[dict[str, Any]] = []
    for name in all_detector_names:
        info = DETECTOR_INFO[name]
        enabled = True  # Default: all enabled
        if config:
            if config.enabled_detectors:
                enabled = name in config.enabled_detectors
            elif config.disabled_detectors:
                enabled = name not in config.disabled_detectors

        # Per-detector provider override
        override = None
        if config and name in config.detector_providers:
            override = config.detector_providers[name]

        detector_states.append({
            "name": name,
            "tier": info["tier"],
            "capability": info["capability"],
            "description": info["description"],
            "enabled": enabled,
            "override_provider": override.provider if override else "",
            "override_model": override.model if override else "",
            "override_capability": override.model_capability if override else "",
        })

    # Aggregate measured model speed from LLM log
    model_speed: dict[str, dict[str, Any]] = {}
    model_class_speed: dict[str, dict[str, Any]] = {}
    conn = _get_conn(request.app)
    if conn is not None:
        from sentinel.store.llm_log import get_model_speed_stats

        try:
            model_speed = get_model_speed_stats(conn)
        except Exception:
            logger.debug("Could not load model speed stats", exc_info=True)

    # Map per-model stats to model class IDs (handles multi-model examples
    # like "gpt-5.4-mini, Claude Haiku 4.5")
    if model_speed:
        for mc in MODEL_CLASSES:
            example_models = [m.strip() for m in mc["example"].split(",")]
            matched = [model_speed[m] for m in example_models if m in model_speed]
            if matched:
                total_tokens = sum(m["total_tokens"] for m in matched)
                total_calls = sum(m["calls"] for m in matched)
                # Weighted average tok/s across matched models
                weighted = sum(
                    m["avg_tok_s"] * m["calls"] for m in matched
                )
                avg_tok_s = round(weighted / total_calls, 1) if total_calls else 0
                model_class_speed[mc["id"]] = {
                    "avg_tok_s": avg_tok_s,
                    "calls": total_calls,
                    "total_tokens": total_tokens,
                }

    return templates.TemplateResponse(request, "compatibility.html", {
        "model_classes": MODEL_CLASSES,
        "llm_rows": llm_rows,
        "det_rows": det_rows,
        "judge_row": judge_row,
        "detector_states": detector_states,
        "config": config,
        "repo_path": repo_path,
        "has_config_file": has_config_file,
        "saved": request.query_params.get("saved") == "1",
        "model_class_speed": model_class_speed,
    })


async def _detectors_save(request: Request, repo_path: str, detector_info: dict[str, Any]) -> Response:
    """Handle POST to save detector toggles and per-detector overrides."""
    import re

    from sentinel.config import (
        _VALID_CAPABILITIES,
        ProviderOverride,
        load_config,
        save_config,
    )

    if not repo_path:
        return Response("No repo configured — cannot save settings", status_code=400)

    repo = Path(repo_path)
    if not repo.is_dir():
        return Response(f"Repository path not found: {repo_path}", status_code=400)

    form = await request.form()
    config = load_config(repo)

    # Detector toggles — checkboxes named "det_enabled_{name}"
    all_names = sorted(detector_info.keys())
    enabled_dets = []
    for name in all_names:
        if f"det_enabled_{name}" in form:
            enabled_dets.append(name)

    # If all are enabled, clear the list (default = all)
    if set(enabled_dets) == set(all_names):
        config.enabled_detectors = []
        config.disabled_detectors = []
    else:
        # Use disabled_detectors (shorter list, more intuitive)
        disabled = [n for n in all_names if n not in enabled_dets]
        config.enabled_detectors = []
        config.disabled_detectors = disabled

    # Per-detector provider overrides
    _DET_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
    _VALID_PROVIDERS = {"ollama", "openai", "azure"}
    new_overrides: dict[str, ProviderOverride] = {}

    for name in all_names:
        prov = str(form.get(f"override_provider_{name}", "")).strip()
        model = str(form.get(f"override_model_{name}", "")).strip()
        cap = str(form.get(f"override_capability_{name}", "")).strip()

        if prov and prov not in _VALID_PROVIDERS:
            return Response(f"Invalid provider for {name}: {prov}", status_code=400)
        if cap and cap not in _VALID_CAPABILITIES:
            return Response(f"Invalid capability for {name}: {cap}", status_code=400)

        if prov or model or cap:
            new_overrides[name] = ProviderOverride(
                provider=prov, model=model, model_capability=cap,
            )

    config.detector_providers = new_overrides

    try:
        save_config(repo, config)
    except Exception:
        logger.exception("Failed to save detector config")
        return Response("Failed to save — check server logs", status_code=500)

    return RedirectResponse(url="/detectors?saved=1", status_code=303)
