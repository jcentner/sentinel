"""LLM Judge — evaluates findings via Ollama for severity and validity."""

from __future__ import annotations

import json
import logging

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
) -> list[Finding]:
    """Run each finding through the LLM judge for evaluation.

    If Ollama is unavailable, returns findings unchanged (graceful degradation).
    """
    if not findings:
        return findings

    if not check_ollama(ollama_url):
        logger.warning("Ollama not available — passing through raw findings")
        return findings

    judged: list[Finding] = []
    for f in findings:
        try:
            result = _judge_single(f, model, ollama_url)
            judged.append(result)
        except Exception:
            logger.warning("Judge failed for finding: %s — using raw", f.title)
            judged.append(f)

    return judged


def _judge_single(
    finding: Finding, model: str, ollama_url: str
) -> Finding:
    """Send a single finding to the LLM judge and return enriched finding."""
    import httpx

    prompt = _build_prompt(finding)

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

    judgment = _parse_judgment(response_text)
    if judgment:
        finding.context = finding.context or {}
        finding.context["judge"] = judgment

        # Adjust severity if the judge says so
        try:
            new_severity = Severity(judgment["adjusted_severity"])
            finding.severity = new_severity
        except (ValueError, KeyError):
            pass

        # If judge says not real, lower confidence
        if not judgment.get("is_real", True):
            finding.confidence = min(finding.confidence, 0.3)
            finding.context["judge_verdict"] = "likely_false_positive"
        else:
            finding.context["judge_verdict"] = "confirmed"

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


def _parse_judgment(text: str) -> dict | None:
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
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        logger.warning("Failed to parse judge JSON: %s", text[start:end][:200])
        return None
