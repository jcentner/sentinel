"""Inline comment drift detector — compares function/class docstrings against code.

Detects stale docstrings that no longer accurately describe their
function or class. Uses the LLM for semantic comparison:
1. Parse Python files with ast to extract docstring + function body pairs
2. Send each pair to the LLM for binary comparison
3. Produce findings for docstrings flagged as "needs review"

This is a per-file analysis (unlike semantic-drift which compares separate
doc files against separate code files). Python-only for v1.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import sqlite3
import textwrap
from pathlib import Path
from typing import Any

from sentinel.core.compatibility import should_use_enhanced_prompt
from sentinel.core.provider import ModelProvider
from sentinel.detectors.base import COMMON_SKIP_DIRS, Detector
from sentinel.models import (
    CapabilityTier,
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    ScopeType,
    Severity,
)

logger = logging.getLogger(__name__)

# Truncation limits for LLM prompt content
_MAX_DOCSTRING_CHARS = 600
_MAX_CODE_CHARS = 1500
_MAX_DOCSTRING_CHARS_ENHANCED = 1200
_MAX_CODE_CHARS_ENHANCED = 3000

# Minimum docstring length to bother analyzing (skip trivial docstrings)
_MIN_DOCSTRING_CHARS = 30

# Maximum number of docstrings to analyze per file (limit LLM cost)
_MAX_PER_FILE = 20

# Maximum number of docstrings to analyze per scan (hard limit)
_MAX_PER_SCAN = 100


class InlineCommentDrift(Detector):
    """Detect stale docstrings that don't match their function/class code."""

    @property
    def name(self) -> str:
        return "inline-comment-drift"

    @property
    def description(self) -> str:
        return "Detects docstrings that no longer accurately describe their code"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.LLM_ASSISTED

    @property
    def capability_tier(self) -> CapabilityTier:
        return CapabilityTier.BASIC

    @property
    def categories(self) -> list[str]:
        return ["docs-drift"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._scan(context)
        except Exception:
            logger.exception("inline-comment-drift detector failed")
            return []

    def _scan(self, context: DetectorContext) -> list[Finding]:
        if context.config.get("skip_llm"):
            logger.debug(
                "skip_llm set — inline-comment-drift detector disabled"
            )
            return []

        provider: ModelProvider | None = context.config.get("provider")
        if provider is None:
            logger.debug(
                "No model provider — inline-comment-drift detector disabled"
            )
            return []

        if not provider.check_health():
            logger.debug(
                "Model provider unavailable — inline-comment-drift disabled"
            )
            return []

        repo_root = Path(context.repo_root)
        py_files = self._get_python_files(context, repo_root)
        if not py_files:
            return []

        # Sort by risk if signals available (high-churn files first)
        if context.risk_signals:
            py_files = _sort_by_risk(py_files, repo_root, context.risk_signals)

        raw_cap = context.config.get("model_capability", "basic")
        model_name = getattr(provider, "model", "")
        use_enhanced = should_use_enhanced_prompt(
            model_name, "inline-comment-drift", raw_cap,
        )
        num_ctx = context.config.get("num_ctx", 2048)

        findings: list[Finding] = []
        total_checked = 0

        for py_file in py_files:
            if total_checked >= _MAX_PER_SCAN:
                break

            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            pairs = extract_docstring_pairs(source)
            if not pairs:
                continue

            rel_path = str(py_file.relative_to(repo_root))

            for pair in pairs[:_MAX_PER_FILE]:
                if total_checked >= _MAX_PER_SCAN:
                    break
                total_checked += 1

                result = self._llm_compare(
                    pair["docstring"],
                    pair["code"],
                    rel_path,
                    pair["name"],
                    pair["line_start"],
                    provider=provider,
                    num_ctx=num_ctx,
                    conn=context.conn,
                    run_id=context.run_id,
                    use_enhanced=use_enhanced,
                )

                if result and result.get("needs_review"):
                    reason = result.get(
                        "reason",
                        "Docstring may not match implementation",
                    )
                    severity = Severity.MEDIUM
                    llm_severity = result.get("severity", "")
                    if llm_severity == "high":
                        severity = Severity.HIGH
                    elif llm_severity == "low":
                        severity = Severity.LOW
                    confidence = 0.70 if use_enhanced else 0.55

                    findings.append(Finding(
                        detector=self.name,
                        category="docs-drift",
                        severity=severity,
                        confidence=confidence,
                        title=(
                            f"Stale docstring: {pair['name']} "
                            f"in {rel_path}"
                        ),
                        description=(
                            f"The docstring for `{pair['name']}` in "
                            f"{rel_path} (line {pair['line_start']}) may "
                            f"not accurately describe the current "
                            f"implementation: {reason}"
                        ),
                        evidence=[
                            Evidence(
                                type=EvidenceType.DOC,
                                source=rel_path,
                                content=pair["docstring"][:500],
                                line_range=(
                                    pair["line_start"],
                                    pair["docstring_end"],
                                ),
                            ),
                            Evidence(
                                type=EvidenceType.CODE,
                                source=rel_path,
                                content=pair["code"][:500],
                                line_range=(
                                    pair["code_start"],
                                    pair["code_end"],
                                ),
                            ),
                        ],
                        file_path=rel_path,
                        line_start=pair["line_start"],
                        line_end=pair["code_end"],
                        context={
                            "pattern": "inline-comment-drift",
                            "symbol_name": pair["name"],
                            "llm_reason": reason,
                            **({"enhanced": True} if use_enhanced else {}),
                        },
                    ))

        return findings

    # ── File discovery ─────────────────────────────────────────────

    @staticmethod
    def _get_python_files(
        context: DetectorContext, repo_root: Path,
    ) -> list[Path]:
        """Get Python files to analyze."""
        if context.scope == ScopeType.TARGETED and context.target_paths:
            return [
                repo_root / p
                for p in context.target_paths
                if p.endswith(".py") and (repo_root / p).is_file()
            ]

        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            return [
                repo_root / f
                for f in context.changed_files
                if f.endswith(".py") and (repo_root / f).is_file()
            ]

        files: list[Path] = []
        for py_file in sorted(repo_root.rglob("*.py")):
            if any(part in COMMON_SKIP_DIRS for part in py_file.parts):
                continue
            files.append(py_file)
        return files

    # ── LLM comparison ─────────────────────────────────────────────

    @staticmethod
    def _llm_compare(
        docstring: str,
        code: str,
        file_path: str,
        symbol_name: str,
        line_start: int,
        *,
        provider: ModelProvider,
        num_ctx: int = 2048,
        conn: sqlite3.Connection | None = None,
        run_id: int | None = None,
        use_enhanced: bool = False,
    ) -> dict[str, Any] | None:
        """Ask the LLM whether a docstring accurately describes its code."""
        if use_enhanced:
            max_doc = _MAX_DOCSTRING_CHARS_ENHANCED
            max_code = _MAX_CODE_CHARS_ENHANCED
        else:
            max_doc = _MAX_DOCSTRING_CHARS
            max_code = _MAX_CODE_CHARS

        doc_text = docstring[:max_doc]
        code_text = code[:max_code]

        if use_enhanced:
            prompt = (
                "You are a senior code documentation reviewer. Analyze whether "
                "the docstring below accurately describes the function/class "
                "implementation.\n\n"
                "Check for:\n"
                "1. Wrong parameter names, types, or missing parameters\n"
                "2. Incorrect return type or behavior description\n"
                "3. Described behavior that the code no longer implements\n"
                "4. Missing important side effects or exceptions\n"
                "5. Wrong usage examples in the docstring\n\n"
                "Ignore: style differences, brevity, and missing type hints "
                "(being brief is not inaccurate).\n\n"
                f"## Docstring for `{symbol_name}` ({file_path}:{line_start})\n"
                f'"""\n{doc_text}\n"""\n\n'
                f"## Implementation\n"
                f"```python\n{code_text}\n```\n\n"
                "Respond ONLY with a JSON object:\n"
                '{"needs_review": true/false, "severity": "high"/"medium"/"low", '
                '"reason": "One sentence if needs_review is true, empty string if '
                'false"}'
            )
            max_tokens = 1024
        else:
            prompt = (
                "You are a code documentation accuracy checker. Compare the "
                "docstring below against the actual function/class "
                "implementation.\n\n"
                "Flag it ONLY if the docstring makes factually wrong claims "
                "about what the code does — wrong parameters, wrong return "
                "values, described behavior that doesn't exist in the code.\n\n"
                "Do NOT flag if the docstring is merely brief, uses different "
                "wording, or omits some details. Being incomplete is not the "
                "same as being wrong.\n\n"
                f"## Docstring for `{symbol_name}` ({file_path}:{line_start})\n"
                f'"""\n{doc_text}\n"""\n\n'
                f"## Implementation\n"
                f"```python\n{code_text}\n```\n\n"
                "Respond ONLY with a JSON object (no markdown fences, no "
                "explanation outside JSON):\n"
                '{"needs_review": true/false, "reason": "One sentence if '
                'needs_review is true, empty string if false"}'
            )
            max_tokens = 512

        try:
            llm_resp = provider.generate(
                prompt,
                temperature=0.1,
                max_tokens=max_tokens,
                num_ctx=num_ctx,
            )
        except Exception:
            logger.debug(
                "LLM call failed for inline-comment-drift: %s:%d",
                file_path, line_start, exc_info=True,
            )
            return None

        text = llm_resp.text.strip()
        tokens = llm_resp.token_count or 0
        gen_ms = llm_resp.duration_ms or 0.0
        logger.debug(
            "inline-comment-drift LLM response (%d tokens): %s",
            tokens, text[:300],
        )

        # Parse JSON from response
        result = None
        try:
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
        except (json.JSONDecodeError, AttributeError):
            pass

        # Log to DB
        if conn is not None:
            verdict = "no_parse"
            if result is not None:
                verdict = (
                    "needs_review"
                    if result.get("needs_review")
                    else "in_sync"
                )
            from sentinel.store.llm_log import LLMLogEntry, insert_llm_log
            try:
                insert_llm_log(
                    conn,
                    run_id,
                    LLMLogEntry(
                        purpose="inline-comment-drift-comparison",
                        model=getattr(provider, "model", str(provider)),
                        detector="inline-comment-drift",
                        finding_title=f"{symbol_name} in {file_path}",
                        prompt=prompt,
                        response=text if text else None,
                        tokens_generated=tokens if tokens is not None else None,
                        generation_ms=gen_ms if gen_ms is not None else None,
                        verdict=verdict,
                        summary=result.get("reason") if result else None,
                    ),
                )
            except Exception:
                logger.debug(
                    "Failed to write inline-comment-drift LLM log",
                    exc_info=True,
                )

        return result


# ── AST extraction ─────────────────────────────────────────────────


def extract_docstring_pairs(source: str) -> list[dict[str, Any]]:
    """Extract (docstring, code) pairs from Python source.

    Returns a list of dicts with keys:
    - name: function/class name
    - docstring: the docstring text
    - code: the function/class body (without the docstring)
    - line_start: line number of the function/class def
    - docstring_end: line number where docstring ends
    - code_start: line number where code body starts
    - code_end: line number of the last line of the function/class
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    pairs: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        docstring = ast.get_docstring(node, clean=True)
        if not docstring or len(docstring) < _MIN_DOCSTRING_CHARS:
            continue

        # Get the body lines excluding the docstring
        body_nodes = node.body[1:]  # skip docstring node
        if not body_nodes:
            continue  # trivial function with only a docstring

        # Determine line ranges
        line_start = node.lineno
        end_lineno = node.end_lineno or node.lineno

        # Docstring node is the first body element
        ds_node = node.body[0]
        docstring_end = ds_node.end_lineno or ds_node.lineno

        # Code body starts after docstring
        code_start = body_nodes[0].lineno
        code_end = end_lineno

        # Extract function/class body code (excluding docstring)
        if code_start <= code_end <= len(lines):
            body_text = "\n".join(lines[code_start - 1 : code_end])
            body_text = textwrap.dedent(body_text)
        else:
            continue

        pairs.append({
            "name": node.name,
            "docstring": docstring,
            "code": body_text,
            "line_start": line_start,
            "docstring_end": docstring_end,
            "code_start": code_start,
            "code_end": code_end,
        })

    return pairs


# Risk signal thresholds (same as test_coherence for consistency)
_FIX_HEAVY_BONUS = 10.0
_FIX_RATIO_THRESHOLD = 0.3


def _sort_by_risk(
    files: list[Path],
    repo_root: Path,
    risk_signals: dict[str, dict[str, Any]],
) -> list[Path]:
    """Sort files by risk score (highest first) to prioritize LLM budget."""
    def risk_key(p: Path) -> float:
        rel = str(p.relative_to(repo_root))
        sig = risk_signals.get(rel, {})
        churn = sig.get("churn_commits", 0)
        fix_ratio = sig.get("churn_fix_ratio", 0.0)
        bonus = _FIX_HEAVY_BONUS if fix_ratio > _FIX_RATIO_THRESHOLD else 0.0
        return float(churn) + bonus

    return sorted(files, key=risk_key, reverse=True)
