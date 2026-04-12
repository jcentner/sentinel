"""Index status page — shows embedding index health."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import Response

from sentinel.web.shared import _get_conn, templates

logger = logging.getLogger(__name__)


async def index_page(request: Request) -> Response:
    """Show embedding index status — file count, chunk count, model."""
    conn = _get_conn(request.app)
    repo_path = getattr(request.app.state, "repo_path", None) or ""

    from sentinel.store.embeddings import chunk_count, get_indexed_files, get_meta

    try:
        files = get_indexed_files(conn, repo_path=repo_path)
        chunks = chunk_count(conn, repo_path=repo_path)
        embed_model = get_meta(conn, "embed_model")
    except Exception:
        logger.debug("Could not load index stats", exc_info=True)
        files = set()
        chunks = 0
        embed_model = None

    return templates.TemplateResponse(request, "embed_index.html", {
        "file_count": len(files),
        "chunk_count": chunks,
        "embed_model": embed_model,
        "repo_path": repo_path,
    })
