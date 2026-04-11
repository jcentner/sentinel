"""Settings display and editing routes."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from sentinel.config import SentinelConfig, load_config, save_config
from sentinel.web.shared import templates

logger = logging.getLogger(__name__)


async def settings_page(request: Request) -> Response:
    """Display current configuration (GET) or save changes (POST)."""
    repo_path = getattr(request.app.state, "repo_path", None) or ""

    if request.method == "POST":
        return await _settings_save(request, repo_path)

    if repo_path:
        config = load_config(Path(repo_path))
        config_file = Path(repo_path) / "sentinel.toml"
        has_config_file = config_file.exists()
    else:
        config = SentinelConfig()
        has_config_file = False

    env_vars = {
        v: bool(os.environ.get(v))
        for v in ["SENTINEL_GITHUB_OWNER", "SENTINEL_GITHUB_REPO", "SENTINEL_GITHUB_TOKEN"]
    }

    return templates.TemplateResponse(request, "settings.html", {
        "config": config,
        "repo_path": repo_path,
        "has_config_file": has_config_file,
        "env_vars": env_vars,
        "saved": request.query_params.get("saved") == "1",
    })


async def _settings_save(request: Request, repo_path: str) -> Response:
    """Handle POST to save settings to sentinel.toml."""
    from sentinel.config import _VALID_CAPABILITIES

    if not repo_path:
        return Response("No repo configured — cannot save settings", status_code=400)

    repo = Path(repo_path)
    if not repo.is_dir():
        return Response(f"Repository path not found: {repo_path}", status_code=400)

    form = await request.form()
    config = load_config(repo)

    # Apply form values to config — only set fields that are present in the form
    _EDITABLE_STR_FIELDS = {
        "provider", "model", "ollama_url", "api_base", "api_key_env",
        "embed_model", "detectors_dir", "output_dir", "db_path",
    }
    _EDITABLE_INT_FIELDS = {"num_ctx", "embed_chunk_size", "embed_chunk_overlap"}
    _EDITABLE_FLOAT_FIELDS = {"min_confidence"}
    _EDITABLE_BOOL_FIELDS = {"skip_judge", "skip_llm"}

    for fname in _EDITABLE_STR_FIELDS:
        val = form.get(fname)
        if val is not None:
            setattr(config, fname, str(val).strip())

    for fname in _EDITABLE_INT_FIELDS:
        val = form.get(fname)
        if val is not None:
            try:
                setattr(config, fname, int(str(val).strip()))
            except ValueError:
                return Response(f"Invalid integer for {fname}: {val}", status_code=400)

    for fname in _EDITABLE_FLOAT_FIELDS:
        val = form.get(fname)
        if val is not None:
            try:
                setattr(config, fname, float(str(val).strip()))
            except ValueError:
                return Response(f"Invalid number for {fname}: {val}", status_code=400)

    for fname in _EDITABLE_BOOL_FIELDS:
        # Checkboxes: present = true, absent = false
        setattr(config, fname, fname in form)

    # Capability tier
    cap = str(form.get("model_capability", "")).strip()
    if cap:
        if cap not in _VALID_CAPABILITIES:
            return Response(f"Invalid capability: {cap}", status_code=400)
        config.model_capability = cap

    # Provider validation
    _VALID_PROVIDERS = {"ollama", "openai", "azure"}
    if config.provider and config.provider not in _VALID_PROVIDERS:
        return Response(f"Invalid provider: {config.provider}", status_code=400)

    # Enabled/disabled detectors (comma-separated text input)
    enabled_raw = str(form.get("enabled_detectors", "")).strip()
    disabled_raw = str(form.get("disabled_detectors", "")).strip()
    config.enabled_detectors = [d.strip() for d in enabled_raw.split(",") if d.strip()] if enabled_raw else []
    config.disabled_detectors = [d.strip() for d in disabled_raw.split(",") if d.strip()] if disabled_raw else []

    if config.enabled_detectors and config.disabled_detectors:
        return Response(
            "Cannot set both enabled and disabled detectors — use one or the other",
            status_code=400,
        )

    try:
        save_config(repo, config)
    except Exception:
        logger.exception("Failed to save config")
        return Response("Failed to save settings — check server logs", status_code=500)

    # Redirect with success indicator
    return RedirectResponse(url="/settings?saved=1", status_code=303)
