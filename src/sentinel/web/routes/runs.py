"""Run listing and detail routes."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from sentinel.models import Finding
from sentinel.store.findings import get_findings_by_run
from sentinel.store.runs import get_run_by_id, get_run_history
from sentinel.web.shared import _get_conn, templates


async def runs_list(request: Request) -> Response:
    """Show all past runs."""
    conn = _get_conn(request.app)
    runs = get_run_history(conn, limit=100)
    return templates.TemplateResponse(request, "runs.html", {"runs": runs})


async def run_detail(request: Request) -> Response:
    """Show findings for a specific run, with optional filters."""
    conn = _get_conn(request.app)
    run_id = int(request.path_params["run_id"])
    run = get_run_by_id(conn, run_id)
    if run is None:
        return Response("Run not found", status_code=404)

    findings = get_findings_by_run(conn, run_id)

    # Get other runs for comparison dropdown
    other_runs = [r for r in get_run_history(conn, limit=20) if r.id != run_id]

    # Read filter query params
    filter_severity = request.query_params.get("severity", "")
    filter_status = request.query_params.get("status", "")
    filter_detector = request.query_params.get("detector", "")

    # Collect unique values for filter dropdowns
    all_detectors = sorted({f.detector for f in findings})
    all_statuses = sorted({f.status.value for f in findings})

    # Compute unfiltered severity counts for stat cards
    from collections import Counter
    total_counts = Counter(f.severity.value for f in findings)

    # Apply filters
    if filter_severity:
        findings = [f for f in findings if f.severity.value == filter_severity]
    if filter_status:
        findings = [f for f in findings if f.status.value == filter_status]
    if filter_detector:
        findings = [f for f in findings if f.detector == filter_detector]

    # Group by severity for display
    grouped: dict[str, list[Finding]] = {"critical": [], "high": [], "medium": [], "low": []}
    for f in findings:
        grouped.setdefault(f.severity.value, []).append(f)

    # Cluster findings within each severity group
    from sentinel.core.clustering import FindingCluster, cluster_by_pattern, cluster_findings

    clustered: dict[str, list[Finding | FindingCluster]] = {}
    for sev, sev_findings in grouped.items():
        pattern_result = cluster_by_pattern(sev_findings)
        remaining = [item for item in pattern_result if isinstance(item, Finding)]
        pattern_clusters = [item for item in pattern_result if isinstance(item, FindingCluster)]
        dir_result = cluster_findings(remaining)
        combined: list[Finding | FindingCluster] = list(pattern_clusters)
        combined.extend(dir_result)
        clustered[sev] = combined

    return templates.TemplateResponse(request, "run_detail.html", {
        "run": run,
        "findings": findings,
        "grouped": grouped,
        "clustered": clustered,
        "total_counts": dict(total_counts),
        "filter_severity": filter_severity,
        "filter_status": filter_status,
        "filter_detector": filter_detector,
        "all_detectors": all_detectors,
        "all_statuses": all_statuses,
        "other_runs": other_runs,
    })


async def run_compare(request: Request) -> Response:
    """Compare findings between two runs."""
    from sentinel.store.findings import compare_runs

    conn = _get_conn(request.app)
    run_id = int(request.path_params["run_id"])
    base_run_id = int(request.path_params["base_run_id"])

    run = get_run_by_id(conn, run_id)
    base_run = get_run_by_id(conn, base_run_id)
    if not run or not base_run:
        return Response("Run not found", status_code=404)

    new_findings, resolved_findings, persistent_findings = compare_runs(
        conn, base_run_id, run_id
    )

    return templates.TemplateResponse(request, "run_compare.html", {
        "run": run,
        "base_run": base_run,
        "new_findings": new_findings,
        "resolved_findings": resolved_findings,
        "persistent_findings": persistent_findings,
    })
