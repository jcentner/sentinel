"""Scan form and trigger routes."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from sentinel.web.shared import _get_conn, templates

logger = logging.getLogger(__name__)

_DET_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_VALID_PROVIDERS = {"ollama", "openai", "azure"}


async def scan_page(request: Request) -> Response:
    """Show scan form (GET) or trigger a scan (POST)."""
    if request.method == "GET":
        from sentinel.detectors.base import get_detector_info

        current_repo = getattr(request.app.state, "repo_path", "") or ""
        detector_info = get_detector_info()
        return templates.TemplateResponse(request, "scan.html", {
            "current_repo": current_repo,
            "detectors": sorted(detector_info, key=lambda d: d["name"]),
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

    repo = Path(repo_path).resolve()
    if user_provided and not repo.is_dir():
        return Response(f"Repository path not found: {repo_path}", status_code=400)

    # TD-025: Validate scan path against allowed roots
    if user_provided:
        allowed_roots = getattr(request.app.state, "allowed_scan_roots", None)
        if allowed_roots:
            repo_resolved = str(repo)
            if not any(repo_resolved.startswith(str(Path(r).resolve())) for r in allowed_roots):
                return Response(
                    "Scan path not within allowed roots", status_code=403
                )

    config = load_config(repo)

    # Incremental scan support
    from sentinel.models import Finding, RunSummary, ScopeType

    scan_scope = ScopeType.FULL
    scan_changed_files: list[str] | None = None
    if form.get("incremental"):
        from sentinel.core.runner import prepare_incremental

        scan_scope, scan_changed_files = prepare_incremental(str(repo), conn)

    # Apply form overrides
    form_model = str(form.get("model", "")).strip()
    if form_model:
        config.model = form_model
    form_embed = str(form.get("embed_model", "")).strip()
    if form_embed:
        config.embed_model = form_embed
    if form.get("skip_judge"):
        config.skip_judge = True
    form_provider = str(form.get("provider", "")).strip()
    if form_provider:
        if form_provider not in _VALID_PROVIDERS:
            return Response(f"Invalid provider: {form_provider}", status_code=400)
        config.provider = form_provider
    form_capability = str(form.get("capability", "")).strip()
    if form_capability:
        from sentinel.config import _VALID_CAPABILITIES

        if form_capability not in _VALID_CAPABILITIES:
            return Response(f"Invalid capability: {form_capability}", status_code=400)
        config.model_capability = form_capability

    # Detector selection from checkboxes
    selected_detectors = form.getlist("detectors")
    if selected_detectors:
        for det_name in selected_detectors:
            if not _DET_NAME_RE.match(str(det_name)):
                return Response(f"Invalid detector name: {det_name}", status_code=400)
        config.enabled_detectors = [str(d) for d in selected_detectors]

    # Per-detector model overrides from the form
    from sentinel.config import _VALID_CAPABILITIES, ProviderOverride

    override_dets = form.getlist("override_detector[]")
    override_providers = form.getlist("override_provider[]")
    override_models = form.getlist("override_model[]")
    override_caps = form.getlist("override_capability[]")
    for i in range(len(override_dets)):
        det_name = str(override_dets[i]).strip() if i < len(override_dets) else ""
        if not det_name:
            continue
        if not _DET_NAME_RE.match(det_name):
            return Response(f"Invalid detector name in override: {det_name}", status_code=400)
        prov = str(override_providers[i]).strip() if i < len(override_providers) else ""
        model = str(override_models[i]).strip() if i < len(override_models) else ""
        cap = str(override_caps[i]).strip() if i < len(override_caps) else ""
        if prov and prov not in _VALID_PROVIDERS:
            return Response(f"Invalid provider in override: {prov}", status_code=400)
        if cap and cap not in _VALID_CAPABILITIES:
            return Response(f"Invalid capability in override: {cap}", status_code=400)
        if prov or model or cap:
            config.detector_providers[det_name] = ProviderOverride(
                provider=prov,
                model=model,
                model_capability=cap,
            )

    def _do_scan() -> tuple[RunSummary, list[Finding], str]:
        from sentinel.core.provider import create_provider

        provider = create_provider(config)
        return run_scan(
            str(repo),
            conn,
            scope=scan_scope,
            changed_files=scan_changed_files,
            provider=provider,
            skip_judge=config.skip_judge,
            embed_model=config.embed_model,
            embed_chunk_size=config.embed_chunk_size,
            embed_chunk_overlap=config.embed_chunk_overlap,
            num_ctx=config.num_ctx,
            detectors_dir=config.detectors_dir,
            output_dir=config.output_dir,
            model_capability=config.model_capability,
            enabled_detectors=config.enabled_detectors or None,
            disabled_detectors=config.disabled_detectors or None,
            sentinel_config=config if config.detector_providers else None,
        )

    try:
        run_summary, _findings, _report_path = await anyio.to_thread.run_sync(_do_scan)
    except Exception:
        logger.exception("Scan failed")
        return Response("Scan failed — check server logs", status_code=500)

    if request.headers.get("hx-request"):
        return Response(
            f'<a href="/runs/{run_summary.id}">Scan complete — view run #{run_summary.id}</a>',
            media_type="text/html",
        )
    return RedirectResponse(url=f"/runs/{run_summary.id}", status_code=303)
