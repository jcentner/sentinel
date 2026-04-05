"""LLM Judge — evaluates findings via Ollama for severity and validity."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from sentinel.core.ollama import check_ollama
from sentinel.models import Finding, Severity

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "qwen3.5:4b"
_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_TIMEOUT = 60.0


def judge_findings(
    findings: list[Finding],
    model: str = _DEFAULT_MODEL,
    ollama_url: str = _DEFAULT_OLLAMA_URL,
    conn: sqlite3.Connection | None = None,
    run_id: int | None = None,
) -> list[Finding]:
    """Run each finding through the LLM judge for evaluation.

    If Ollama is unavailable, returns findings unchanged (graceful degradation).
    When *conn* is provided, each LLM interaction is logged to the llm_log table.
    """
    if not findings:
        return findings

    if not check_ollama(ollama_url):
        logger.warning("Ollama not available — passing through raw findings")
        return findings

    logger.info("Judging %d findings with model=%s", len(findings), model)
    judged: list[Finding] = []
    confirmed = 0
    rejected = 0
    errored = 0
    total_time = 0.0
    for i, f in enumerate(findings, 1):
        prompt = _build_prompt(f)
        try:
            t0 = time.monotonic()
            result = _judge_single(f, model, ollama_url, prompt=prompt, conn=conn, run_id=run_id)
            elapsed = time.monotonic() - t0
            total_time += elapsed
            verdict = result.context.get("judge_verdict", "unknown") if result.context else "no_parse"
            if verdict == "confirmed":
                confirmed += 1
            elif verdict == "likely_false_positive":
                rejected += 1
            logger.info(
                "  [%d/%d] %s → %s (%.1fs)",
                i, len(findings), f.title[:60], verdict, elapsed,
            )
            judged.append(result)
        except Exception:
            errored += 1
            logger.warning("Judge failed for finding: %s — using raw", f.title)
            _log_llm_entry(conn, run_id, model, f, purpose="judge",
                           prompt=prompt, verdict="error")
            judged.append(f)

    logger.info(
        "Judge complete: %d confirmed, %d likely_fp, %d errors (%.1fs total)",
        confirmed, rejected, errored, total_time,
    )
    return judged


def _judge_single(
    finding: Finding,
    model: str,
    ollama_url: str,
    *,
    prompt: str,
    conn: sqlite3.Connection | None = None,
    run_id: int | None = None,
) -> Finding:
    """Send a single finding to the LLM judge and return enriched finding."""
    import httpx

    logger.debug("Judge prompt for '%s':\n%s", finding.title[:60], prompt)

    resp = httpx.post(
        f"{ollama_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()

    data = resp.json()
    response_text = data.get("response", "")
    tokens = data.get("eval_count", 0)
    gen_time_ns = data.get("eval_duration", 0)
    gen_ms = gen_time_ns / 1e6
    logger.debug("Judge raw response for '%s' (%d tokens, %.0fms):\n%s",
                 finding.title[:60], tokens, gen_ms, response_text[:500])

    judgment = _parse_judgment(response_text)
    verdict = "no_parse"
    if judgment:
        finding.context = finding.context or {}
        finding.context["judge"] = judgment

        # Adjust severity if the judge says so
        old_severity = finding.severity
        try:
            new_severity = Severity(judgment["adjusted_severity"])
            finding.severity = new_severity
        except (ValueError, KeyError):
            pass

        # If judge says not real, lower confidence
        if not judgment.get("is_real", True):
            finding.confidence = min(finding.confidence, 0.3)
            finding.context["judge_verdict"] = "likely_false_positive"
            verdict = "likely_false_positive"
        else:
            finding.context["judge_verdict"] = "confirmed"
            verdict = "confirmed"

        if finding.severity != old_severity:
            logger.debug("Judge adjusted severity: %s → %s for '%s'",
                         old_severity.value, finding.severity.value, finding.title[:60])
        summary = judgment.get("summary", "")
        if summary:
            logger.debug("Judge summary for '%s': %s", finding.title[:60], summary)
    else:
        logger.debug("Judge returned no parseable judgment for '%s'", finding.title[:60])

    _log_llm_entry(
        conn, run_id, model, finding,
        purpose="judge",
        prompt=prompt,
        response=response_text,
        tokens=tokens,
        gen_ms=gen_ms,
        verdict=verdict,
        judgment=judgment,
    )

    return finding


def _build_prompt(finding: Finding) -> str:
    """Build the judge prompt from a finding."""
    evidence_text = ""
    for e in finding.evidence:
        evidence_text += f"\n### {e.type.value} from {e.source}\n```\n{e.content}\n```\n"

    if not evidence_text:
        evidence_text = "(no evidence)"

    # Use f-string instead of .format() to avoid crashes when evidence
    # content contains { or } characters (e.g., JSON, dicts, f-strings)
    return (
        "You are a code quality judge. Analyze this finding from an automated "
        "code scanner and determine if it represents a real issue worth addressing.\n\n"
        "## Finding\n"
        f"- **Detector**: {finding.detector}\n"
        f"- **Category**: {finding.category}\n"
        f"- **Severity (detector's assessment)**: {finding.severity.value}\n"
        f"- **Confidence**: {finding.confidence}\n"
        f"- **Title**: {finding.title}\n"
        f"- **Description**: {finding.description}\n"
        f"- **File**: {finding.file_path or '(none)'}\n"
        f"- **Line**: {finding.line_start or '(none)'}\n\n"
        "## Evidence\n"
        f"{evidence_text}\n\n"
        "## Your Task\n"
        "Respond ONLY with a JSON object (no markdown, no explanation):\n"
        '{\n'
        '  "is_real": true/false,\n'
        '  "adjusted_severity": "low"/"medium"/"high"/"critical",\n'
        '  "summary": "One sentence explaining your judgment",\n'
        '  "reasoning": "Brief reasoning for your assessment"\n'
        '}'
    )


def _parse_judgment(text: str) -> dict[str, Any] | None:
    """Parse the JSON judgment from the LLM response."""
    # Try to extract JSON from the response
    text = text.strip()

    # Handle markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        logger.warning("No JSON found in judge response")
        return None

    try:
        result: dict[str, Any] = json.loads(text[start:end])
        return result
    except json.JSONDecodeError:
        logger.warning("Failed to parse judge JSON: %s", text[start:end][:200])
        return None


def _log_llm_entry(
    conn: sqlite3.Connection | None,
    run_id: int | None,
    model: str,
    finding: Finding,
    *,
    purpose: str = "judge",
    prompt: str = "",
    response: str = "",
    tokens: int = 0,
    gen_ms: float = 0.0,
    verdict: str = "error",
    judgment: dict[str, Any] | None = None,
) -> None:
    """Persist an LLM interaction to the llm_log table if conn is available."""
    if conn is None:
        return
    from sentinel.store.llm_log import LLMLogEntry, insert_llm_log

    entry = LLMLogEntry(
        purpose=purpose,
        model=model,
        detector=finding.detector,
        finding_fingerprint=finding.fingerprint,
        finding_title=finding.title,
        prompt=prompt,
        response=response if response else None,
        tokens_generated=tokens if tokens is not None else None,
        generation_ms=gen_ms if gen_ms is not None else None,
        verdict=verdict,
        is_real=judgment.get("is_real") if judgment else None,
        adjusted_severity=judgment.get("adjusted_severity") if judgment else None,
        summary=judgment.get("summary") if judgment else None,
    )
    try:
        insert_llm_log(conn, run_id, entry)
    except Exception:
        logger.debug("Failed to write LLM log entry", exc_info=True)
