"""Semantic docs-drift detector — compares documentation prose against referenced source code.

Unlike the deterministic docs-drift detector (which finds broken links and stale references),
this detector uses the LLM to identify **semantic** inconsistencies: documentation that
describes behavior or APIs that no longer match the actual code.

Strategy:
1. Parse markdown into heading-delimited sections
2. Find file/function references in each section
3. Extract relevant code from referenced files (Python ast, regex for others)
4. Send (doc section + code excerpt) to LLM for binary comparison
5. Produce findings for sections flagged as "needs review"
"""

from __future__ import annotations

import ast
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from sentinel.core.provider import ModelProvider
from sentinel.detectors.base import COMMON_SKIP_DIRS, Detector
from sentinel.models import (
    CapabilityTier,
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)

logger = logging.getLogger(__name__)

# ── Markdown section parsing ──────────────────────────────────────

# Match heading lines: # Heading, ## Heading, ### Heading (up to h3)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

# ── Reference extraction patterns ─────────────────────────────────

# File paths in backticks: `src/sentinel/config.py`, `models.py`
_BACKTICK_PATH = re.compile(r"`([\w./-]+\.(?:py|js|ts|go|rs|toml|yaml|yml|json|cfg))`")

# Bare file paths in prose: src/sentinel/config.py (must start with src/ or similar)
_PROSE_PATH = re.compile(
    r"\b((?:src|lib|pkg|cmd|internal|app)/[\w./-]+\.(?:py|js|ts|go|rs))\b"
)

# Function/class names in backticks: `run_scan()`, `SentinelConfig`, `detect()`
_BACKTICK_SYMBOL = re.compile(r"`(\w{2,}(?:\(\))?)`")

# Markdown links to source files: [config.py](src/sentinel/config.py)
_MD_LINK_PATH = re.compile(
    r"\[[^\]]*\]\(([\w./-]+\.(?:py|js|ts|go|rs))\)"
)

# Key doc filenames to scan
_KEY_DOCS = frozenset({
    "README.MD", "CONTRIBUTING.MD", "INSTALL.MD", "GETTING-STARTED.MD",
    "USAGE.MD", "API.MD", "DEVELOPMENT.MD", "GUIDE.MD",
    "QUICKSTART.MD", "SETUP.MD",
})

# Max chars for doc section and code excerpt sent to LLM
_MAX_DOC_CHARS = 800
_MAX_CODE_CHARS = 2000
# Extended limits for standard+ capability
_MAX_DOC_CHARS_ENHANCED = 1500
_MAX_CODE_CHARS_ENHANCED = 3000

# Min section length to bother analyzing (skip trivial headings)
_MIN_SECTION_CHARS = 50


class SemanticDriftDetector(Detector):
    """Detect semantic inconsistencies between documentation prose and source code."""

    @property
    def name(self) -> str:
        return "semantic-drift"

    @property
    def description(self) -> str:
        return "Compare documentation sections against referenced source code for semantic drift"

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
            logger.exception("semantic-drift detector failed")
            return []

    def _scan(self, context: DetectorContext) -> list[Finding]:
        if context.config.get("skip_llm"):
            logger.debug("skip_llm set — semantic-drift detector disabled")
            return []

        repo_root = Path(context.repo_root)
        provider: ModelProvider | None = context.config.get("provider")
        if provider is None:
            logger.debug("No model provider — semantic-drift detector disabled")
            return []

        if not provider.check_health():
            logger.debug("Model provider unavailable — semantic-drift detector disabled")
            return []

        md_files = self._get_key_docs(context, repo_root)
        if not md_files:
            logger.debug("No key doc files found")
            return []

        findings: list[Finding] = []
        model_cap = context.config.get("model_capability", "basic")
        use_enhanced = model_cap in ("standard", "advanced")

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel_path = str(md_file.relative_to(repo_root))
            sections = parse_sections(content)
            logger.debug(
                "semantic-drift: %d sections in %s", len(sections), rel_path
            )

            for section in sections:
                pairs = extract_code_pairs(section, repo_root)
                if not pairs:
                    continue

                for code_path, code_excerpt in pairs:
                    if use_enhanced:
                        result = self._llm_compare_enhanced(
                            section["title"],
                            section["body"],
                            rel_path,
                            code_path,
                            code_excerpt,
                            provider=provider,
                            num_ctx=context.config.get("num_ctx", 2048),
                            conn=context.conn,
                            run_id=context.run_id,
                        )
                    else:
                        result = self._llm_compare(
                            section["title"],
                            section["body"],
                            rel_path,
                            code_path,
                            code_excerpt,
                            provider=provider,
                            num_ctx=context.config.get("num_ctx", 2048),
                            conn=context.conn,
                            run_id=context.run_id,
                        )
                    if result and result.get("needs_review"):
                        reason = result.get(
                            "reason", "Documentation may not match implementation"
                        )
                        # Enhanced mode provides specifics and severity
                        specifics = result.get("specifics", [])
                        specifics_text = ""
                        if specifics:
                            specifics_text = "\n\nSpecifics:\n" + "\n".join(
                                f"  - {s}" for s in specifics
                            )
                        severity = Severity.MEDIUM
                        llm_severity = result.get("severity", "")
                        if llm_severity == "high":
                            severity = Severity.HIGH
                        elif llm_severity == "low":
                            severity = Severity.LOW
                        confidence = 0.75 if use_enhanced else 0.6

                        findings.append(
                            Finding(
                                detector=self.name,
                                category="docs-drift",
                                severity=severity,
                                confidence=confidence,
                                title=(
                                    f"Semantic drift: \"{section['title']}\" "
                                    f"vs {code_path}"
                                ),
                                description=(
                                    f"LLM analysis found potential semantic drift "
                                    f"between the \"{section['title']}\" section in "
                                    f"{rel_path} and source code in {code_path}: "
                                    f"{reason}{specifics_text}"
                                ),
                                evidence=[
                                    Evidence(
                                        type=EvidenceType.DOC,
                                        source=rel_path,
                                        content=section["body"][:500],
                                        line_range=(
                                            section["line_start"],
                                            section["line_end"],
                                        ),
                                    ),
                                    Evidence(
                                        type=EvidenceType.CODE,
                                        source=code_path,
                                        content=code_excerpt[:500],
                                    ),
                                ],
                                file_path=rel_path,
                                line_start=section["line_start"],
                                line_end=section["line_end"],
                                context={
                                    "pattern": "semantic-drift",
                                    "section_title": section["title"],
                                    "code_path": code_path,
                                    "llm_reason": reason,
                                    **({"specifics": specifics} if specifics else {}),
                                    **({"enhanced": True} if use_enhanced else {}),
                                },
                            )
                        )

        return findings

    # ── File discovery ─────────────────────────────────────────────

    @staticmethod
    def _get_key_docs(
        context: DetectorContext, repo_root: Path
    ) -> list[Path]:
        """Find key documentation files to analyze.

        Intentionally shallow: only scans repo root and docs/ directory to bound
        LLM cost per scan. See phase-5-semantic-detectors.md.
        """
        if context.scope.value == "targeted" and context.target_paths:
            return [
                repo_root / p
                for p in context.target_paths
                if (repo_root / p).is_file() and p.upper().rstrip("/").split("/")[-1] in _KEY_DOCS
            ]

        if context.scope.value == "incremental" and context.changed_files:
            return [
                repo_root / p
                for p in context.changed_files
                if (repo_root / p).is_file()
                and p.upper().rstrip("/").split("/")[-1] in _KEY_DOCS
            ]

        results: list[Path] = []
        for item in sorted(repo_root.iterdir()):
            if item.is_file() and item.suffix.lower() == ".md" and item.name.upper() in _KEY_DOCS:
                results.append(item)

        # Also check docs/ directory one level down
        docs_dir = repo_root / "docs"
        if docs_dir.is_dir():
            for item in sorted(docs_dir.iterdir()):
                if item.is_file() and item.suffix.lower() == ".md" and item.name.upper() in _KEY_DOCS:
                    results.append(item)

        return results

    # ── LLM comparison ─────────────────────────────────────────────

    @staticmethod
    def _llm_compare(
        section_title: str,
        section_body: str,
        doc_path: str,
        code_path: str,
        code_excerpt: str,
        *,
        provider: ModelProvider,
        num_ctx: int = 2048,
        conn: sqlite3.Connection | None = None,
        run_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Ask the LLM whether a doc section accurately describes the referenced code."""
        doc_text = section_body[:_MAX_DOC_CHARS]
        code_text = code_excerpt[:_MAX_CODE_CHARS]

        prompt = (
            "You are a documentation accuracy reviewer. Compare the documentation section "
            "below against the actual source code. Determine whether the documentation "
            "ACCURATELY describes the code's current behavior, API, parameters, and usage.\n\n"
            "Focus on factual accuracy: wrong parameter names, missing parameters, incorrect "
            "return types, outdated behavior descriptions, wrong class/function names, or "
            "described features that no longer exist in the code.\n\n"
            "Ignore style differences, minor wording choices, and documentation that is "
            "simply less detailed than the code (being brief is not inaccurate).\n\n"
            f'## Documentation section: "{section_title}" (from {doc_path})\n'
            f"{doc_text}\n\n"
            f"## Source code (from {code_path})\n"
            f"```\n{code_text}\n```\n\n"
            "Respond ONLY with a JSON object (no markdown fences, no explanation outside JSON):\n"
            '{"needs_review": true/false, "reason": "One sentence if needs_review is true, '
            'empty string if false"}'
        )

        try:
            llm_resp = provider.generate(
                prompt,
                temperature=0.1,
                max_tokens=512,
                num_ctx=num_ctx,
            )
        except Exception:
            logger.debug(
                "LLM call failed for semantic-drift: %s vs %s",
                doc_path, code_path, exc_info=True,
            )
            return None

        text = llm_resp.text.strip()
        tokens = llm_resp.token_count or 0
        gen_ms = llm_resp.duration_ms or 0.0
        logger.debug(
            "Semantic-drift LLM response (%d tokens): %s",
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
                verdict = "needs_review" if result.get("needs_review") else "in_sync"
            from sentinel.store.llm_log import LLMLogEntry, insert_llm_log
            try:
                insert_llm_log(
                    conn,
                    run_id,
                    LLMLogEntry(
                        purpose="semantic-drift-comparison",
                        model=getattr(provider, "model", str(provider)),
                        detector="semantic-drift",
                        finding_title=f'"{section_title}" vs {code_path}',
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
                    "Failed to write semantic-drift LLM log entry", exc_info=True
                )

        return result

    @staticmethod
    def _llm_compare_enhanced(
        section_title: str,
        section_body: str,
        doc_path: str,
        code_path: str,
        code_excerpt: str,
        *,
        provider: ModelProvider,
        num_ctx: int = 2048,
        conn: sqlite3.Connection | None = None,
        run_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Enhanced comparison using standard+ tier model.

        Returns structured analysis with specific inaccuracies and severity.
        """
        doc_text = section_body[:_MAX_DOC_CHARS_ENHANCED]
        code_text = code_excerpt[:_MAX_CODE_CHARS_ENHANCED]

        prompt = (
            "You are a senior documentation accuracy reviewer. Analyze the "
            "documentation section below against the actual source code.\n\n"
            "Check for:\n"
            "1. Wrong parameter names, types, or missing parameters\n"
            "2. Incorrect return type or behavior description\n"
            "3. Outdated class/function names or removed features\n"
            "4. Wrong usage examples or code snippets\n"
            "5. Missing important caveats or preconditions\n"
            "6. Described configuration or options that no longer exist\n\n"
            "Ignore: style differences, brevity (being brief is not inaccurate), "
            "and documentation that accurately describes a subset of behavior.\n\n"
            f'## Documentation section: "{section_title}" (from {doc_path})\n'
            f"{doc_text}\n\n"
            f"## Source code (from {code_path})\n"
            f"```\n{code_text}\n```\n\n"
            "Respond ONLY with a JSON object (no markdown fences, no explanation "
            "outside JSON):\n"
            "{\n"
            '  "needs_review": true/false,\n'
            '  "severity": "low" | "medium" | "high",\n'
            '  "reason": "One-sentence summary of the main issue (empty if in sync)",\n'
            '  "specifics": ["Each specific inaccuracy or outdated claim"]\n'
            "}\n\n"
            "Severity guide:\n"
            "- high: factually wrong API/parameter/behavior info that will mislead developers\n"
            "- medium: outdated descriptions or missing important details\n"
            "- low: minor omissions or slightly stale wording"
        )

        try:
            llm_resp = provider.generate(
                prompt,
                temperature=0.1,
                max_tokens=1024,
                num_ctx=num_ctx,
            )
        except Exception:
            logger.debug(
                "Enhanced LLM call failed for semantic-drift: %s vs %s",
                doc_path, code_path, exc_info=True,
            )
            return None

        text = llm_resp.text.strip()
        tokens = llm_resp.token_count or 0
        gen_ms = llm_resp.duration_ms or 0.0
        logger.debug(
            "Semantic-drift enhanced LLM response (%d tokens): %s",
            tokens, text[:500],
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
                verdict = "needs_review" if result.get("needs_review") else "in_sync"
            from sentinel.store.llm_log import LLMLogEntry, insert_llm_log
            try:
                insert_llm_log(
                    conn,
                    run_id,
                    LLMLogEntry(
                        purpose="semantic-drift-enhanced",
                        model=getattr(provider, "model", str(provider)),
                        detector="semantic-drift",
                        finding_title=f'"{section_title}" vs {code_path}',
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
                    "Failed to write semantic-drift enhanced LLM log entry",
                    exc_info=True,
                )

        return result


# ── Section parsing (module-level for testability) ─────────────────


def parse_sections(content: str) -> list[dict[str, Any]]:
    """Split markdown content into heading-delimited sections.

    Returns a list of dicts with keys: title, body, line_start, line_end, level.
    Only sections with body text ≥ MIN_SECTION_CHARS are included.
    """
    lines = content.split("\n")
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            # Close previous section
            if current is not None:
                current["line_end"] = i  # exclusive — last line of body
                body = "\n".join(lines[current["body_start"] : i]).strip()
                current["body"] = body
                if len(body) >= _MIN_SECTION_CHARS:
                    sections.append(current)

            current = {
                "title": m.group(2).strip(),
                "level": len(m.group(1)),
                "line_start": i + 1,  # 1-indexed for Finding.line_start
                "body_start": i + 1,  # 0-indexed into lines[] (next line after heading)
            }

    # Close last section
    if current is not None:
        current["line_end"] = len(lines)
        body = "\n".join(lines[current["body_start"] :]).strip()
        current["body"] = body
        if len(body) >= _MIN_SECTION_CHARS:
            sections.append(current)

    # Remove internal bookkeeping key
    for s in sections:
        s.pop("body_start", None)

    return sections


def extract_code_pairs(
    section: dict[str, Any], repo_root: Path
) -> list[tuple[str, str]]:
    """Find source files referenced in a doc section and extract relevant code.

    Returns list of (relative_path, code_excerpt) tuples.
    """
    body = section["body"]
    referenced_paths: set[str] = set()

    # 1. Find file paths in backticks: `src/sentinel/config.py`
    for m in _BACKTICK_PATH.finditer(body):
        referenced_paths.add(m.group(1))

    # 2. Find file paths in prose: src/sentinel/config.py
    for m in _PROSE_PATH.finditer(body):
        referenced_paths.add(m.group(1))

    # 3. Find markdown links to source files: [config.py](src/sentinel/config.py)
    for m in _MD_LINK_PATH.finditer(body):
        referenced_paths.add(m.group(1))

    # Resolve and validate paths
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    for ref_path in sorted(referenced_paths):
        full_path = repo_root / ref_path
        if not full_path.is_file():
            continue
        # Skip if in a common skip dir
        try:
            rel = full_path.relative_to(repo_root)
        except ValueError:
            continue
        if any(part in COMMON_SKIP_DIRS for part in rel.parts):
            continue

        rel_str = str(rel)
        if rel_str in seen:
            continue
        seen.add(rel_str)

        excerpt = _extract_code_excerpt(full_path)
        if excerpt:
            pairs.append((rel_str, excerpt))

    # 4. If no file paths found, try to match backtick symbols to files
    if not pairs:
        symbols = _extract_symbols(body)
        if symbols:
            pairs = _match_symbols_to_files(symbols, repo_root)

    return pairs


def _extract_symbols(body: str) -> list[str]:
    """Extract function/class names from backtick-wrapped identifiers."""
    symbols: list[str] = []
    for m in _BACKTICK_SYMBOL.finditer(body):
        name = m.group(1).rstrip("()")
        # Skip common non-symbol words and short names
        if len(name) < 3:
            continue
        if name.lower() in {
            "true", "false", "none", "null", "str", "int", "float", "bool",
            "list", "dict", "set", "tuple", "any", "the", "and", "for",
            "var", "let", "const", "map", "new", "this", "self", "return",
            "import", "from", "with", "class", "type", "string", "number",
            "make", "func", "async", "await", "yield", "print", "error",
        }:
            continue
        symbols.append(name)
    return symbols


def _match_symbols_to_files(
    symbols: list[str], repo_root: Path
) -> list[tuple[str, str]]:
    """Try to find source files containing the referenced symbols.

    Walks Python source files in the repo looking for function/class definitions
    matching the symbol names. Returns at most 3 matches to limit LLM calls.
    """
    pairs: list[tuple[str, str]] = []
    target_names = {s.lower() for s in symbols}

    src_dirs = [repo_root / "src", repo_root / "lib", repo_root]
    searched: set[Path] = set()

    for src_dir in src_dirs:
        if not src_dir.is_dir():
            continue
        for py_file in sorted(src_dir.rglob("*.py")):
            if py_file in searched:
                continue
            searched.add(py_file)

            try:
                rel = py_file.relative_to(repo_root)
            except ValueError:
                continue
            if any(part in COMMON_SKIP_DIRS for part in rel.parts):
                continue

            try:
                source = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            # Quick check: does this file define any of the target symbols?
            found = False
            for sym in target_names:
                if re.search(rf"(?:def|class)\s+{re.escape(sym)}\b", source, re.IGNORECASE):
                    found = True
                    break

            if found:
                excerpt = _extract_code_excerpt(py_file)
                if excerpt:
                    pairs.append((str(rel), excerpt))
                    if len(pairs) >= 3:
                        return pairs

    return pairs


def _extract_code_excerpt(file_path: Path) -> str | None:
    """Extract a meaningful code excerpt from a source file.

    For Python files: uses ast to extract function/class signatures with docstrings.
    For other files: takes the first ~80 lines.
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    if not source.strip():
        return None

    if file_path.suffix == ".py":
        return _extract_python_signatures(source)

    # For non-Python: take first lines, skipping large files
    lines = source.split("\n")
    if len(lines) > 500:
        # For large files, try to extract function-like signatures
        sig_lines = _extract_generic_signatures(lines)
        if sig_lines:
            return sig_lines
    return "\n".join(lines[:80])


def _extract_python_signatures(source: str) -> str | None:
    """Extract function and class signatures with docstrings using Python ast."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fall back to first 80 lines if unparseable
        lines = source.split("\n")
        return "\n".join(lines[:80])

    parts: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_function_sig(node, source)
            if sig:
                parts.append(sig)
        elif isinstance(node, ast.ClassDef):
            sig = _format_class_sig(node, source)
            if sig:
                parts.append(sig)

    if not parts:
        # No functions or classes — return first lines
        lines = source.split("\n")
        return "\n".join(lines[:80])

    result = "\n\n".join(parts)
    return result[:_MAX_CODE_CHARS]


def _format_function_sig(
    node: ast.FunctionDef | ast.AsyncFunctionDef, source: str
) -> str | None:
    """Format a function signature with its docstring."""
    lines = source.split("\n")
    # Get the def line(s)
    start = node.lineno - 1
    # Find end of signature (could span multiple lines due to args)
    end = start + 1
    if node.body:
        end = node.body[0].lineno - 1
    sig_lines = lines[start:min(end, start + 5)]
    sig = "\n".join(sig_lines).rstrip()

    # Get docstring if present
    docstring = ast.get_docstring(node)
    if docstring:
        # Truncate long docstrings
        if len(docstring) > 200:
            docstring = docstring[:200] + "..."
        return f"{sig}\n    \"\"\"{docstring}\"\"\""
    return sig


def _format_class_sig(node: ast.ClassDef, source: str) -> str | None:
    """Format a class definition with its docstring and method signatures."""
    lines = source.split("\n")
    start = node.lineno - 1
    class_line = lines[start].rstrip()

    parts = [class_line]

    # Get class docstring
    docstring = ast.get_docstring(node)
    if docstring:
        if len(docstring) > 200:
            docstring = docstring[:200] + "..."
        parts.append(f'    """{docstring}"""')

    # Get method signatures (just the def line, not bodies)
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_line = lines[item.lineno - 1].rstrip() if item.lineno - 1 < len(lines) else None
            if method_line:
                parts.append(f"    {method_line.strip()}")

    return "\n".join(parts)


def _extract_generic_signatures(lines: list[str]) -> str | None:
    """Extract function-like signatures from non-Python source files."""
    # Match common function declaration patterns
    func_re = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:pub\s+)?(?:fn|func|function|def)\s+\w+",
    )
    sig_lines: list[str] = []
    for i, line in enumerate(lines):
        if func_re.match(line):
            # Take the function line and up to 2 lines of context
            end = min(i + 3, len(lines))
            sig_lines.extend(lines[i:end])
            sig_lines.append("")

    if not sig_lines:
        return None
    return "\n".join(sig_lines[:60])
