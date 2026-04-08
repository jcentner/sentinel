"""Finding cluster synthesis — LLM-powered root-cause analysis of finding groups.

After the judge evaluates individual findings, the synthesizer groups related
findings into clusters and asks the LLM to identify root causes, redundancies,
and actionable recommendations.  This collapses many symptoms into fewer
actionable items for the morning report.

Requires ``model_capability >= standard``.  When disabled or unavailable,
findings pass through unchanged.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field

from sentinel.core.clustering import cluster_by_pattern
from sentinel.core.provider import ModelProvider
from sentinel.models import Finding

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a code quality analyst reviewing groups of related findings "
    "from a repository health scanner. Your job is to identify root causes, "
    "flag redundant findings, and suggest the single action that addresses "
    "the underlying issue."
)


@dataclass
class SynthesisResult:
    """Result of synthesizing a cluster of findings."""

    root_cause: str
    recommended_action: str
    redundant_fingerprints: list[str] = field(default_factory=list)
    confidence: float = 0.7


def synthesize_clusters(
    findings: list[Finding],
    *,
    provider: ModelProvider,
    conn: sqlite3.Connection | None = None,
    run_id: int | None = None,
    num_ctx: int = 2048,
    min_cluster_size: int = 3,
) -> list[Finding]:
    """Synthesize clusters of related findings via LLM.

    Groups findings by pattern (same detector + normalized title), sends
    each cluster to the LLM for root-cause analysis, and annotates
    findings with synthesis data in their ``context`` dict.

    Findings not part of any cluster are returned unchanged.
    Returns all findings (both synthesized and standalone).
    """
    if not findings:
        return findings

    if not provider.check_health():
        logger.warning("Provider not available for synthesis — skipping")
        return findings

    # Cluster by pattern (detector + normalized title)
    items = cluster_by_pattern(findings, min_size=min_cluster_size)

    clusters_processed = 0
    findings_synthesized = 0
    total_time = 0.0

    result_findings: list[Finding] = []
    for item in items:
        if isinstance(item, Finding):
            result_findings.append(item)
            continue

        # item is a FindingCluster
        cluster_findings_list = item.findings
        prompt = _build_synthesis_prompt(cluster_findings_list, item.pattern_label)

        try:
            t0 = time.monotonic()
            synthesis = _synthesize_single(
                cluster_findings_list, provider, prompt=prompt,
                conn=conn, run_id=run_id, num_ctx=num_ctx,
            )
            elapsed = time.monotonic() - t0
            total_time += elapsed
            clusters_processed += 1

            # Annotate each finding in the cluster with synthesis data
            redundant_set = set(synthesis.redundant_fingerprints)
            for f in cluster_findings_list:
                if f.context is None:
                    f.context = {}
                f.context["synthesis"] = {
                    "root_cause": synthesis.root_cause,
                    "recommended_action": synthesis.recommended_action,
                    "cluster_label": item.pattern_label,
                    "cluster_size": len(cluster_findings_list),
                }
                if f.fingerprint and f.fingerprint in redundant_set:
                    f.context["synthesis"]["redundant"] = True
                findings_synthesized += 1

            logger.info(
                "Cluster %r: %d findings, %d redundant (%.1fs)",
                item.pattern_label[:50],
                len(cluster_findings_list),
                len(redundant_set),
                elapsed,
            )
        except Exception:
            logger.warning(
                "Synthesis failed for cluster %r — passing through",
                item.pattern_label[:50], exc_info=True,
            )

        result_findings.extend(cluster_findings_list)

    if clusters_processed:
        logger.info(
            "Synthesis complete: %d clusters, %d findings annotated (%.1fs total)",
            clusters_processed, findings_synthesized, total_time,
        )

    return result_findings


def _build_synthesis_prompt(findings: list[Finding], label: str) -> str:
    """Build the synthesis prompt for a cluster of findings."""
    parts = [
        f"## Finding Cluster: {label}",
        f"This cluster contains {len(findings)} related findings.",
        "",
        "### Findings",
    ]

    for i, f in enumerate(findings, 1):
        evidence_str = ""
        if f.evidence:
            ev = f.evidence[0]
            content = ev.content[:300] if ev.content else ""
            evidence_str = f"\n  Evidence: {ev.source}: {content}"

        parts.append(
            f"{i}. [{f.severity.value}] {f.title}\n"
            f"   File: {f.file_path or '(no file)'}\n"
            f"   Fingerprint: {f.fingerprint or 'none'}"
            f"{evidence_str}"
        )

    parts.append("")
    parts.append("### Your Task")
    parts.append(
        "Analyze these findings as a group. Respond ONLY with JSON:\n"
        "{\n"
        '  "root_cause": "One-sentence description of the shared root cause",\n'
        '  "recommended_action": "The single action that fixes most of these",\n'
        '  "redundant_fingerprints": ["fp1", "fp2"],\n'
        '  "confidence": 0.0-1.0\n'
        "}\n\n"
        "redundant_fingerprints: list fingerprints of findings that are "
        "duplicates at a semantic level (same root cause, same fix). "
        "Keep the most informative one and mark the rest as redundant."
    )

    return "\n".join(parts)


def _synthesize_single(
    findings: list[Finding],
    provider: ModelProvider,
    *,
    prompt: str,
    conn: sqlite3.Connection | None = None,
    run_id: int | None = None,
    num_ctx: int = 2048,
) -> SynthesisResult:
    """Send a single cluster to the LLM and return the synthesis result."""
    llm_resp = provider.generate(
        prompt,
        system=_SYSTEM_PROMPT,
        temperature=0.2,
        max_tokens=1024,
        num_ctx=num_ctx,
        json_output=True,
    )

    response_text = llm_resp.text
    tokens = llm_resp.token_count or 0
    gen_ms = llm_resp.duration_ms or 0.0

    logger.debug(
        "Synthesis response (%d tokens, %.0fms): %s",
        tokens, gen_ms, response_text[:500],
    )

    # Log to LLM log table
    if conn is not None and run_id is not None:
        _log_synthesis(
            conn, run_id, str(provider), findings,
            prompt=prompt, response=response_text,
            tokens=tokens, duration_ms=gen_ms,
        )

    # Parse JSON response
    result = _parse_synthesis(response_text)
    if result is None:
        logger.warning("Failed to parse synthesis response — using default")
        return SynthesisResult(
            root_cause="Unable to determine root cause",
            recommended_action="Review findings individually",
        )
    return result


def _parse_synthesis(text: str) -> SynthesisResult | None:
    """Parse the synthesis JSON response."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    # Find JSON boundaries
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None

    root_cause = data.get("root_cause", "")
    if not root_cause:
        return None

    return SynthesisResult(
        root_cause=root_cause,
        recommended_action=data.get("recommended_action", ""),
        redundant_fingerprints=data.get("redundant_fingerprints", []),
        confidence=float(data.get("confidence", 0.7)),
    )


def _log_synthesis(
    conn: sqlite3.Connection,
    run_id: int,
    provider_name: str,
    findings: list[Finding],
    *,
    prompt: str,
    response: str,
    tokens: int,
    duration_ms: float,
) -> None:
    """Log synthesis LLM interaction to the llm_log table."""
    try:
        from sentinel.store.llm_log import insert_llm_log

        insert_llm_log(conn, {
            "run_id": run_id,
            "provider": provider_name,
            "model": "",
            "purpose": "synthesis",
            "finding_title": f"cluster:{len(findings)} findings",
            "finding_fingerprint": findings[0].fingerprint or "" if findings else "",
            "prompt_text": prompt[:4000],
            "response_text": response[:4000],
            "token_count": tokens,
            "duration_ms": duration_ms,
            "verdict": "synthesized",
        })
    except Exception:
        logger.debug("Failed to log synthesis entry", exc_info=True)
