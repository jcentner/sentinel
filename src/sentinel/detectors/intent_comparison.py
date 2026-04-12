"""Intent comparison detector — multi-artifact triangulation for contradiction detection.

For each function/symbol, gathers up to four independent sources of intent:
1. Code body — what it actually does
2. Docstring — inline documentation of what it should do
3. Test function(s) — what the tests verify
4. Doc section — external documentation describing the function

When three or more artifacts are available, sends them to the LLM in a single
prompt asking for contradictions between *any* pair. This catches inconsistencies
that pairwise detectors (semantic-drift, test-coherence, inline-comment-drift)
miss because they only compare two artifacts at a time.

Cap: ADVANCED — needs a frontier-class model for reliable multi-artifact reasoning.
Python-only for v1.
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

# ── Truncation limits ──────────────────────────────────────────────

_MAX_CODE_CHARS = 1200
_MAX_DOCSTRING_CHARS = 500
_MAX_TEST_CHARS = 800
_MAX_DOC_CHARS = 600

_MAX_CODE_CHARS_ENHANCED = 2500
_MAX_DOCSTRING_CHARS_ENHANCED = 1000
_MAX_TEST_CHARS_ENHANCED = 1500
_MAX_DOC_CHARS_ENHANCED = 1200

# Minimum artifact sizes — skip trivial content
_MIN_DOCSTRING_CHARS = 30
_MIN_CODE_LINES = 3
_MIN_TEST_LINES = 3

# Budget limits
_MAX_PER_FILE = 10
_MAX_PER_SCAN = 50

# Minimum artifacts required for triangulation (code body always present,
# so _MIN_ARTIFACTS=3 means code + 2 others)
_MIN_ARTIFACTS = 3

# Risk signal thresholds (same as other LLM detectors)
_FIX_HEAVY_BONUS = 10.0
_FIX_RATIO_THRESHOLD = 0.3

# Test file detection
_TEST_FILE_RE = re.compile(r"^test_\w+\.py$|^\w+_test\.py$")

# Doc file detection
_DOC_EXTENSIONS = frozenset({".md", ".rst"})

# Heading regex for markdown section parsing
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

# Min section body to consider
_MIN_SECTION_CHARS = 50

# Symbol reference in backticks: `run_scan()`, `SentinelConfig`
_BACKTICK_SYMBOL_RE = re.compile(r"`(\w{2,})(?:\(\))?`")


class IntentComparisonDetector(Detector):
    """Detect contradictions across code, docstrings, tests, and documentation."""

    @property
    def name(self) -> str:
        return "intent-comparison"

    @property
    def description(self) -> str:
        return (
            "Multi-artifact triangulation: finds contradictions between "
            "code, docstrings, tests, and documentation"
        )

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.LLM_ASSISTED

    @property
    def capability_tier(self) -> CapabilityTier:
        return CapabilityTier.ADVANCED

    @property
    def categories(self) -> list[str]:
        return ["cross-artifact"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._scan(context)
        except Exception:
            logger.exception("intent-comparison detector failed")
            return []

    # ── Main scan logic ────────────────────────────────────────────

    def _scan(self, context: DetectorContext) -> list[Finding]:
        if context.config.get("skip_llm"):
            logger.debug("skip_llm set — intent-comparison detector disabled")
            return []

        provider: ModelProvider | None = context.config.get("provider")
        if provider is None:
            logger.debug(
                "No model provider — intent-comparison detector disabled"
            )
            return []

        if not provider.check_health():
            logger.debug(
                "Model provider unavailable — intent-comparison disabled"
            )
            return []

        repo_root = Path(context.repo_root)

        # Phase 1: discover Python files to analyze
        py_files = self._get_python_files(context, repo_root)
        if not py_files:
            return []

        # Sort by risk if signals available
        if context.risk_signals:
            py_files = _sort_by_risk(py_files, repo_root, context.risk_signals)

        # Phase 2: build lookup tables for tests and doc sections
        test_lookup = _build_test_lookup(repo_root)
        doc_lookup = _build_doc_lookup(repo_root)

        raw_cap = context.config.get("model_capability", "basic")
        model_name = getattr(provider, "model", "")
        use_enhanced = should_use_enhanced_prompt(
            model_name, "intent-comparison", raw_cap,
        )
        num_ctx = context.config.get("num_ctx", 4096)

        findings: list[Finding] = []
        total_checked = 0

        for py_file in py_files:
            if total_checked >= _MAX_PER_SCAN:
                break

            # Skip test files — we analyze *implementations*, not tests
            if _TEST_FILE_RE.match(py_file.name):
                continue

            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            symbols = _extract_symbols(source)
            if not symbols:
                continue

            rel_path = str(py_file.relative_to(repo_root))

            for sym in symbols[:_MAX_PER_FILE]:
                if total_checked >= _MAX_PER_SCAN:
                    break

                # Gather artifacts
                artifacts = _gather_artifacts(
                    sym, py_file, rel_path, repo_root,
                    test_lookup, doc_lookup,
                )

                # Only triangulate when 3+ artifacts available
                if len(artifacts) < _MIN_ARTIFACTS:
                    continue

                total_checked += 1

                result = _llm_triangulate(
                    sym_name=sym["name"],
                    artifacts=artifacts,
                    file_path=rel_path,
                    line_start=sym["line_start"],
                    provider=provider,
                    num_ctx=num_ctx,
                    conn=context.conn,
                    run_id=context.run_id,
                    use_enhanced=use_enhanced,
                )

                if result and result.get("contradictions"):
                    for contradiction in result["contradictions"]:
                        severity = Severity.MEDIUM
                        llm_sev = contradiction.get("severity", "")
                        if llm_sev == "high":
                            severity = Severity.HIGH
                        elif llm_sev == "low":
                            severity = Severity.LOW

                        pair = contradiction.get("between", [])
                        pair_label = " vs ".join(pair[:2]) if pair else "artifacts"
                        reason = contradiction.get(
                            "reason",
                            "Multiple sources disagree about this function",
                        )

                        confidence = 0.70 if use_enhanced else 0.55

                        evidence_items = _build_evidence(
                            sym, artifacts, pair, rel_path,
                        )

                        findings.append(Finding(
                            detector=self.name,
                            category="cross-artifact",
                            severity=severity,
                            confidence=confidence,
                            title=(
                                f"Intent mismatch ({pair_label}): "
                                f"{sym['name']} in {rel_path}"
                            ),
                            description=(
                                f"Multi-artifact analysis of `{sym['name']}` "
                                f"in {rel_path} (line {sym['line_start']}) "
                                f"found a contradiction between {pair_label}: "
                                f"{reason}"
                            ),
                            evidence=evidence_items,
                            file_path=rel_path,
                            line_start=sym["line_start"],
                            line_end=sym.get("code_end", sym["line_start"]),
                            context={
                                "pattern": "intent-comparison",
                                "symbol_name": sym["name"],
                                "artifact_count": len(artifacts),
                                "contradiction_pair": pair_label,
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
        """Get Python implementation files to analyze."""
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
            if any(part.endswith(".egg-info") for part in py_file.parts):
                continue
            files.append(py_file)
        return files


# ── Symbol extraction ──────────────────────────────────────────────


def _extract_symbols(source: str) -> list[dict[str, Any]]:
    """Extract function/class symbols with their code and docstrings.

    Returns list of dicts with keys: name, docstring, code, line_start,
    code_end, docstring_end, code_start.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    symbols: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue

        line_start = node.lineno
        end_lineno = node.end_lineno or node.lineno

        docstring = ast.get_docstring(node, clean=True)

        # Get the code body (excluding docstring if present)
        body_nodes = node.body[1:] if docstring else node.body

        if not body_nodes:
            continue

        code_start = body_nodes[0].lineno
        code_end = end_lineno

        if code_start <= code_end <= len(lines):
            body_text = "\n".join(lines[code_start - 1 : code_end])
            body_text = textwrap.dedent(body_text)
        else:
            continue

        # Skip trivial functions
        if body_text.count("\n") < _MIN_CODE_LINES:
            continue

        sym: dict[str, Any] = {
            "name": node.name,
            "code": body_text,
            "line_start": line_start,
            "code_start": code_start,
            "code_end": code_end,
        }

        if docstring and len(docstring) >= _MIN_DOCSTRING_CHARS:
            ds_node = node.body[0]
            sym["docstring"] = docstring
            sym["docstring_end"] = ds_node.end_lineno or ds_node.lineno

        symbols.append(sym)

    return symbols


# ── Test lookup ────────────────────────────────────────────────────


def _build_test_lookup(
    repo_root: Path,
) -> dict[str, dict[str, str]]:
    """Build a mapping from implementation function name to test function bodies.

    Returns: {lower_func_name: {test_func_name: test_body, ...}}
    """
    lookup: dict[str, dict[str, str]] = {}

    for py_file in sorted(repo_root.rglob("*.py")):
        if any(part in COMMON_SKIP_DIRS for part in py_file.parts):
            continue
        if any(part.endswith(".egg-info") for part in py_file.parts):
            continue
        if not _TEST_FILE_RE.match(py_file.name):
            continue

        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue

            if not node.name.startswith("test_"):
                continue

            # Derive implementation function name
            base = node.name[5:].lower()  # strip test_ prefix
            if not base:
                continue

            end = node.end_lineno or node.lineno
            if node.lineno - 1 < end <= len(lines):
                body = "\n".join(lines[node.lineno - 1 : end])
            else:
                continue

            if body.count("\n") < _MIN_TEST_LINES:
                continue

            lookup.setdefault(base, {})[node.name] = body

    return lookup


def _find_tests_for_symbol(
    sym_name: str,
    test_lookup: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Find test functions for a symbol using exact and prefix matching.

    Returns {test_func_name: test_body} for matches.
    """
    key = sym_name.lower()

    # Exact match
    if key in test_lookup:
        return test_lookup[key]

    # Prefix match — find tests where the impl name is a prefix
    # e.g. "run_scan" matches test_run_scan_incremental
    matches: dict[str, str] = {}
    for test_key, test_funcs in test_lookup.items():
        if test_key.startswith(key + "_"):
            matches.update(test_funcs)
    return matches


# ── Doc section lookup ─────────────────────────────────────────────


def _build_doc_lookup(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Build a mapping from symbol names to doc sections mentioning them.

    Returns: {lower_symbol_name: [{title, body, file, line_start}, ...]}
    """
    lookup: dict[str, list[dict[str, Any]]] = {}

    for doc_file in sorted(repo_root.rglob("*")):
        if doc_file.suffix.lower() not in _DOC_EXTENSIONS:
            continue
        if any(part in COMMON_SKIP_DIRS for part in doc_file.parts):
            continue
        if any(part.endswith(".egg-info") for part in doc_file.parts):
            continue

        try:
            content = doc_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_path = str(doc_file.relative_to(repo_root))
        sections = _parse_sections(content)

        for section in sections:
            # Find symbol references in backticks
            refs = set()
            for m in _BACKTICK_SYMBOL_RE.finditer(section["body"]):
                refs.add(m.group(1).lower())

            for ref in refs:
                lookup.setdefault(ref, []).append({
                    "title": section["title"],
                    "body": section["body"],
                    "file": rel_path,
                    "line_start": section["line_start"],
                })

    return lookup


def _parse_sections(content: str) -> list[dict[str, Any]]:
    """Split markdown into heading-delimited sections."""
    text_lines = content.split("\n")
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for i, line in enumerate(text_lines):
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                body = "\n".join(
                    text_lines[current["body_start"] : i]
                ).strip()
                if len(body) >= _MIN_SECTION_CHARS:
                    current["body"] = body
                    sections.append(current)
            current = {
                "title": m.group(2).strip(),
                "line_start": i + 1,
                "body_start": i + 1,
            }

    if current is not None:
        body = "\n".join(text_lines[current["body_start"] :]).strip()
        if len(body) >= _MIN_SECTION_CHARS:
            current["body"] = body
            sections.append(current)

    # Remove internal key
    for s in sections:
        s.pop("body_start", None)

    return sections


# ── Artifact gathering ─────────────────────────────────────────────


def _gather_artifacts(
    sym: dict[str, Any],
    py_file: Path,
    rel_path: str,
    repo_root: Path,
    test_lookup: dict[str, dict[str, str]],
    doc_lookup: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Gather all available artifacts for a symbol.

    Returns a dict with keys present only if the artifact exists:
    - "code": str
    - "docstring": str
    - "tests": list[dict] with keys test_name, test_body
    - "doc_sections": list[dict] with keys title, body, file, line_start
    """
    artifacts: dict[str, Any] = {"code": sym["code"]}

    if "docstring" in sym:
        artifacts["docstring"] = sym["docstring"]

    # Find tests
    tests = _find_tests_for_symbol(sym["name"], test_lookup)
    if tests:
        artifacts["tests"] = [
            {"test_name": tn, "test_body": tb}
            for tn, tb in list(tests.items())[:3]  # limit to 3 tests
        ]

    # Find doc sections
    doc_sections = doc_lookup.get(sym["name"].lower(), [])
    if doc_sections:
        artifacts["doc_sections"] = doc_sections[:2]  # limit to 2 sections

    return artifacts


# ── LLM triangulation ──────────────────────────────────────────────


def _llm_triangulate(
    *,
    sym_name: str,
    artifacts: dict[str, Any],
    file_path: str,
    line_start: int,
    provider: ModelProvider,
    num_ctx: int = 4096,
    conn: sqlite3.Connection | None = None,
    run_id: int | None = None,
    use_enhanced: bool = False,
) -> dict[str, Any] | None:
    """Ask the LLM to find contradictions across multiple artifacts."""
    if use_enhanced:
        max_code = _MAX_CODE_CHARS_ENHANCED
        max_doc = _MAX_DOCSTRING_CHARS_ENHANCED
        max_test = _MAX_TEST_CHARS_ENHANCED
        max_doc_section = _MAX_DOC_CHARS_ENHANCED
    else:
        max_code = _MAX_CODE_CHARS
        max_doc = _MAX_DOCSTRING_CHARS
        max_test = _MAX_TEST_CHARS
        max_doc_section = _MAX_DOC_CHARS

    # Build artifact sections for the prompt
    sections: list[str] = []
    artifact_names: list[str] = []

    # Always include code
    sections.append(
        f"## CODE — `{sym_name}` ({file_path}:{line_start})\n"
        f"```python\n{artifacts['code'][:max_code]}\n```"
    )
    artifact_names.append("code")

    if "docstring" in artifacts:
        sections.append(
            f'## DOCSTRING\n"""\n{artifacts["docstring"][:max_doc]}\n"""'
        )
        artifact_names.append("docstring")

    if "tests" in artifacts:
        test_parts = []
        for t in artifacts["tests"]:
            test_parts.append(
                f"### {t['test_name']}\n"
                f"```python\n{t['test_body'][:max_test]}\n```"
            )
        sections.append("## TEST(S)\n" + "\n".join(test_parts))
        artifact_names.append("test")

    if "doc_sections" in artifacts:
        doc_parts = []
        for ds in artifacts["doc_sections"]:
            doc_parts.append(
                f"### {ds['title']} (from {ds['file']})\n{ds['body'][:max_doc_section]}"
            )
        sections.append("## DOCUMENTATION\n" + "\n".join(doc_parts))
        artifact_names.append("documentation")

    artifact_text = "\n\n".join(sections)
    artifact_list = ", ".join(artifact_names)

    if use_enhanced:
        prompt = (
            "You are a senior software engineer performing multi-artifact "
            "consistency analysis. You are given multiple independent sources "
            "of intent for the same function: code, docstring, tests, and/or "
            "documentation.\n\n"
            "Your task: identify **contradictions** between any pair of "
            "artifacts. A contradiction is when two sources make conflicting "
            "claims about what the function does, its parameters, return "
            "values, behavior, or side effects.\n\n"
            "Do NOT flag:\n"
            "- Differences in level of detail (one source being more verbose)\n"
            "- Style differences or different wording for the same concept\n"
            "- Missing coverage (a test not testing every feature)\n"
            "- Cosmetic or formatting differences\n\n"
            "Only flag genuine factual contradictions where two sources "
            "disagree about the function's behavior.\n\n"
            f"Artifacts available: {artifact_list}\n\n"
            f"{artifact_text}\n\n"
            "Respond ONLY with a JSON object:\n"
            "{\n"
            '  "contradictions": [\n'
            '    {"between": ["artifact1", "artifact2"], '
            '"severity": "high"/"medium"/"low", '
            '"reason": "One sentence describing the contradiction"}\n'
            "  ]\n"
            "}\n"
            f"Use these exact names in 'between': {artifact_list}\n"
            "If no contradictions found, return: "
            '{"contradictions": []}'
        )
        max_tokens = 1024
    else:
        prompt = (
            "You are a code consistency checker. Compare these artifacts "
            f"for `{sym_name}` and find factual contradictions between them.\n\n"
            "A contradiction is when two sources disagree about what the "
            "function does. Do NOT flag differences in verbosity, style, "
            "or missing coverage.\n\n"
            f"Artifacts: {artifact_list}\n\n"
            f"{artifact_text}\n\n"
            "Respond ONLY with a JSON object (no markdown fences):\n"
            "{\n"
            '  "contradictions": [\n'
            '    {"between": ["artifact1", "artifact2"], '
            '"reason": "One sentence"}\n'
            "  ]\n"
            "}\n"
            f"Use these exact names in 'between': {artifact_list}\n"
            'If no contradictions: {"contradictions": []}'
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
            "LLM call failed for intent-comparison: %s:%d",
            file_path, line_start, exc_info=True,
        )
        return None

    text = llm_resp.text.strip()
    tokens = llm_resp.token_count or 0
    gen_ms = llm_resp.duration_ms or 0.0
    logger.debug(
        "intent-comparison LLM response (%d tokens): %s",
        tokens, text[:300],
    )

    # Parse JSON
    result = None
    try:
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    # Validate result structure
    if result is not None and not isinstance(result.get("contradictions"), list):
        result = None

    # Log to DB
    if conn is not None:
        verdict = "no_parse"
        if result is not None:
            contradictions = result.get("contradictions", [])
            verdict = (
                "contradiction_found"
                if contradictions
                else "no_contradiction"
            )
        from sentinel.store.llm_log import LLMLogEntry, insert_llm_log
        try:
            insert_llm_log(
                conn,
                run_id,
                LLMLogEntry(
                    purpose="intent-comparison",
                    model=getattr(provider, "model", str(provider)),
                    detector="intent-comparison",
                    finding_title=f"{sym_name} in {file_path}",
                    prompt=prompt,
                    response=text if text else None,
                    tokens_generated=tokens if tokens else None,
                    generation_ms=gen_ms if gen_ms else None,
                    verdict=verdict,
                    summary=(
                        result["contradictions"][0].get("reason")
                        if result and result.get("contradictions")
                        else None
                    ),
                ),
            )
        except Exception:
            logger.debug(
                "Failed to write intent-comparison LLM log",
                exc_info=True,
            )

    return result


# ── Evidence builder ───────────────────────────────────────────────


def _build_evidence(
    sym: dict[str, Any],
    artifacts: dict[str, Any],
    pair: list[str],
    rel_path: str,
) -> list[Evidence]:
    """Build evidence items for a contradiction finding."""
    evidence: list[Evidence] = []

    # Always include the code as primary evidence
    evidence.append(Evidence(
        type=EvidenceType.CODE,
        source=rel_path,
        content=sym["code"][:500],
        line_range=(sym["code_start"], sym["code_end"]),
    ))

    # Add artifacts from the contradiction pair (both sides if available)
    pair_lower = [p.lower() for p in pair]

    # Match leniently: "docstring"/"doc" in pair → docstring artifact
    if (
        any(p.startswith("doc") and p != "documentation" for p in pair_lower)
        and "docstring" in artifacts
    ):
        evidence.append(Evidence(
            type=EvidenceType.DOC,
            source=rel_path,
            content=artifacts["docstring"][:500],
            line_range=(
                sym["line_start"],
                sym.get("docstring_end", sym["line_start"]),
            ),
        ))

    # Match: "test"/"tests" in pair → test artifact
    if any(p.startswith("test") for p in pair_lower) and "tests" in artifacts:
        test = artifacts["tests"][0]
        evidence.append(Evidence(
            type=EvidenceType.TEST,
            source=test["test_name"],
            content=test["test_body"][:500],
        ))

    # Match: "documentation"/"doc_section"/"docs" in pair → doc section
    if (
        any(p in ("documentation", "doc_section", "docs") for p in pair_lower)
        and "doc_sections" in artifacts
    ):
        ds = artifacts["doc_sections"][0]
        evidence.append(Evidence(
            type=EvidenceType.DOC,
            source=ds["file"],
            content=ds["body"][:500],
            line_range=(ds["line_start"], ds["line_start"]),
        ))

    return evidence


# ── Risk sorting ───────────────────────────────────────────────────


def _sort_by_risk(
    files: list[Path],
    repo_root: Path,
    risk_signals: dict[str, dict[str, Any]],
) -> list[Path]:
    """Sort files by risk score (highest first) for LLM budget priority."""
    def risk_key(p: Path) -> float:
        rel = str(p.relative_to(repo_root))
        sig = risk_signals.get(rel, {})
        churn = sig.get("churn_commits", 0)
        fix_ratio = sig.get("churn_fix_ratio", 0.0)
        bonus = _FIX_HEAVY_BONUS if fix_ratio > _FIX_RATIO_THRESHOLD else 0.0
        return float(churn) + bonus

    return sorted(files, key=risk_key, reverse=True)
