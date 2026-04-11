"""Finding detail, actions, and annotation routes."""

from __future__ import annotations

from html import escape

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from sentinel.models import FindingStatus
from sentinel.store.findings import (
    Annotation,
    add_annotation,
    delete_annotation,
    get_annotations,
    get_finding_by_id,
    suppress_finding,
    update_finding_status,
)
from sentinel.web.shared import _get_conn, templates


async def finding_detail(request: Request) -> Response:
    """Show full details of a single finding."""
    conn = _get_conn(request.app)
    finding_id = int(request.path_params["finding_id"])
    finding = get_finding_by_id(conn, finding_id)
    if finding is None:
        return Response("Finding not found", status_code=404)
    annotations = get_annotations(conn, finding_id)
    return templates.TemplateResponse(request, "finding_detail.html", {
        "finding": finding,
        "annotations": annotations,
    })


async def finding_action(request: Request) -> Response:
    """Handle approve/suppress actions via POST (htmx-friendly)."""
    conn = _get_conn(request.app)
    finding_id = int(request.path_params["finding_id"])
    finding = get_finding_by_id(conn, finding_id)
    if finding is None:
        return Response("Finding not found", status_code=404)

    form = await request.form()
    action = form.get("action", "")

    if action == "approve":
        update_finding_status(conn, finding_id, FindingStatus.APPROVED)
    elif action == "suppress":
        if not finding.fingerprint:
            return Response("Finding has no fingerprint", status_code=400)
        reason = str(form.get("reason", "")) or None
        suppress_finding(conn, finding.fingerprint, reason=reason)
    else:
        return Response("Unknown action", status_code=400)

    if request.headers.get("hx-request"):
        new_status = "approved" if action == "approve" else "suppressed"
        return Response(
            f'<span class="badge badge-{new_status}">{new_status}</span>',
            media_type="text/html",
        )

    referer = request.headers.get("referer", "/")
    url = referer if (referer.startswith("/") and not referer.startswith("//")) else "/"
    return RedirectResponse(url=url, status_code=303)


async def annotation_add(request: Request) -> Response:
    """Add a note/annotation to a finding (htmx-friendly)."""
    conn = _get_conn(request.app)
    finding_id = int(request.path_params["finding_id"])
    finding = get_finding_by_id(conn, finding_id)
    if finding is None:
        return Response("Finding not found", status_code=404)

    form = await request.form()
    content = str(form.get("content", "")).strip()
    if not content:
        return Response("Annotation content is required", status_code=400)

    add_annotation(conn, finding_id, content)

    if request.headers.get("hx-request"):
        annotations = get_annotations(conn, finding_id)
        return Response(
            _render_annotations_html(annotations, finding_id),
            media_type="text/html",
        )

    return RedirectResponse(url=f"/findings/{finding_id}", status_code=303)


async def annotation_delete(request: Request) -> Response:
    """Delete an annotation (htmx-friendly)."""
    conn = _get_conn(request.app)
    finding_id = int(request.path_params["finding_id"])
    annotation_id = int(request.path_params["annotation_id"])

    delete_annotation(conn, annotation_id, finding_id)

    if request.headers.get("hx-request"):
        annotations = get_annotations(conn, finding_id)
        return Response(
            _render_annotations_html(annotations, finding_id),
            media_type="text/html",
        )

    return RedirectResponse(url=f"/findings/{finding_id}", status_code=303)


async def bulk_action(request: Request) -> Response:
    """Handle bulk approve/suppress for multiple findings."""
    conn = _get_conn(request.app)
    run_id = int(request.path_params["run_id"])

    form = await request.form()
    action = str(form.get("action", ""))
    finding_ids_raw = form.getlist("finding_ids")

    if action not in ("approve", "suppress"):
        return Response("Unknown action", status_code=400)
    if not finding_ids_raw:
        return Response("No findings selected", status_code=400)

    finding_ids: list[int] = []
    for raw_id in finding_ids_raw:
        try:
            finding_ids.append(int(str(raw_id)))
        except (ValueError, TypeError):
            return Response(f"Invalid finding ID: {raw_id}", status_code=400)

    count = 0
    for fid in finding_ids:
        finding = get_finding_by_id(conn, fid)
        if finding is None:
            continue
        if action == "approve":
            update_finding_status(conn, fid, FindingStatus.APPROVED)
            count += 1
        elif action == "suppress":
            if finding.fingerprint:
                reason = str(form.get("reason", "")) or None
                suppress_finding(conn, finding.fingerprint, reason=reason)
                count += 1

    if request.headers.get("hx-request"):
        past = "approved" if action == "approve" else "suppressed"
        return Response(
            f'<div class="toast toast-success">{count} finding{"s" if count != 1 else ""} {past}</div>',
            headers={"HX-Trigger": "bulkActionComplete"},
            media_type="text/html",
        )
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


def _render_annotations_html(
    annotations: list[Annotation], finding_id: int
) -> str:
    """Render the annotations list as HTML for htmx responses."""
    parts: list[str] = []
    for a in annotations:
        parts.append(
            f'<div class="annotation" id="annotation-{a.id}">'
            f'<p class="annotation-content">{escape(a.content)}</p>'
            f'<div class="annotation-meta">'
            f'<time>{a.created_at.strftime("%Y-%m-%d %H:%M")}</time>'
            f'<form method="post" '
            f'action="/findings/{finding_id}/annotations/{a.id}/delete" '
            f'hx-post="/findings/{finding_id}/annotations/{a.id}/delete" '
            f'hx-target="#annotations-list" hx-swap="innerHTML" '
            f'style="display:inline">'
            f'<button type="submit" class="btn btn-sm btn-danger">'
            f'Delete</button></form></div></div>'
        )
    return "".join(parts)
