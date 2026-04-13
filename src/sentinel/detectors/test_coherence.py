"""Test-code coherence detector — identifies stale tests that no longer validate their implementations.

This detector finds test files, pairs them with the implementation files they test,
extracts matched (test function, implementation function) pairs, and asks the LLM
whether the test meaningfully validates the current implementation.

Strategy:
1. Find test files (files matching test_*.py or *_test.py)
2. Pair each test file with its implementation file (naming convention + import analysis)
3. Extract function-level pairs via ast (test_run_scan → run_scan)
4. Send (test function body + implementation function body) to LLM for binary comparison
5. Produce findings for test functions flagged as "needs review"
"""

from __future__ import annotations

import ast
import json
import logging
import re
import sqlite3
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
    Severity,
)

logger = logging.getLogger(__name__)

# Max chars for test/impl code sent to LLM
_MAX_TEST_CHARS = 1500
_MAX_IMPL_CHARS = 1500
# Extended limits for standard+ capability
_MAX_TEST_CHARS_ENHANCED = 3000
_MAX_IMPL_CHARS_ENHANCED = 3000

# Min function body size to bother analyzing
_MIN_FUNC_LINES = 3

# Max function pairs to analyze per test file (limit LLM calls)
_MAX_PAIRS_PER_FILE = 5

# TD-043: Risk-based sorting thresholds for LLM targeting
_FIX_HEAVY_BONUS = 10.0  # Add to risk score when fix ratio exceeds threshold
_FIX_RATIO_THRESHOLD = 0.3  # Files with >30% fix commits get priority

# Test file patterns
_TEST_FILE_RE = re.compile(r"^test_\w+\.py$|^\w+_test\.py$")


class TestCoherenceDetector(Detector):
    """Detect stale tests that no longer meaningfully validate their implementations."""

    @property
    def name(self) -> str:
        return "test-coherence"

    @property
    def description(self) -> str:
        return "Compare test functions against implementations for staleness"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.LLM_ASSISTED

    @property
    def capability_tier(self) -> CapabilityTier:
        return CapabilityTier.BASIC

    @property
    def categories(self) -> list[str]:
        return ["test-coherence"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._scan(context)
        except Exception:
            logger.exception("test-coherence detector failed")
            return []

    def _scan(self, context: DetectorContext) -> list[Finding]:
        if context.config.get("skip_llm"):
            logger.debug("skip_llm set — test-coherence detector disabled")
            return []

        repo_root = Path(context.repo_root)
        provider: ModelProvider | None = context.config.get("provider")
        if provider is None:
            logger.debug("No model provider — test-coherence detector disabled")
            return []

        if not provider.check_health():
            logger.debug("Model provider unavailable — test-coherence detector disabled")
            return []

        test_files = find_test_files(repo_root)
        if not test_files:
            logger.debug("No test files found")
            return []

        # TD-043: Sort test files by risk — prioritize tests for high-churn
        # implementation files so LLM budget focuses on the riskiest code.
        if context.risk_signals:
            def _impl_risk(tf: Path) -> float:
                impl = find_implementation_file(tf, repo_root)
                if impl is None:
                    return 0.0
                rel = str(impl.relative_to(repo_root))
                sig = context.risk_signals.get(rel)  # type: ignore[union-attr]
                if sig is None:
                    return 0.0
                churn: float = sig.get("churn_commits", 0)
                fix_ratio: float = sig.get("churn_fix_ratio", 0)
                return churn + (_FIX_HEAVY_BONUS if fix_ratio > _FIX_RATIO_THRESHOLD else 0.0)
            test_files.sort(key=_impl_risk, reverse=True)
            logger.debug("test-coherence: sorted %d test files by risk signals", len(test_files))

        findings: list[Finding] = []
        raw_cap = context.config.get("model_capability", "basic")
        model_name = getattr(provider, "model", "")
        use_enhanced = should_use_enhanced_prompt(
            model_name, "test-coherence", raw_cap,
        )

        for test_file in test_files:
            impl_file = find_implementation_file(test_file, repo_root)
            if impl_file is None:
                continue

            pairs = extract_function_pairs(test_file, impl_file)
            if not pairs:
                continue

            test_rel = str(test_file.relative_to(repo_root))
            impl_rel = str(impl_file.relative_to(repo_root))

            for test_name, test_body, impl_name, impl_body in pairs[:_MAX_PAIRS_PER_FILE]:
                if use_enhanced:
                    result = self._llm_compare_enhanced(
                        test_name=test_name,
                        test_body=test_body,
                        impl_name=impl_name,
                        impl_body=impl_body,
                        test_path=test_rel,
                        impl_path=impl_rel,
                        provider=provider,
                        num_ctx=context.config.get("num_ctx", 2048),
                        conn=context.conn,
                        run_id=context.run_id,
                    )
                else:
                    result = self._llm_compare(
                        test_name=test_name,
                        test_body=test_body,
                        impl_name=impl_name,
                        impl_body=impl_body,
                        test_path=test_rel,
                        impl_path=impl_rel,
                        provider=provider,
                        num_ctx=context.config.get("num_ctx", 2048),
                        conn=context.conn,
                        run_id=context.run_id,
                    )
                if result and result.get("needs_review"):
                    reason = result.get(
                        "reason", "Test may not validate the current implementation"
                    )
                    # Enhanced mode provides structured gaps and severity
                    gaps = result.get("gaps", [])
                    gap_text = ""
                    if gaps:
                        gap_text = "\n\nSpecific gaps:\n" + "\n".join(
                            f"  - {g}" for g in gaps
                        )
                    # Use LLM-suggested severity if available
                    severity = Severity.MEDIUM
                    llm_severity = result.get("severity", "")
                    if llm_severity == "high":
                        severity = Severity.HIGH
                    elif llm_severity == "low":
                        severity = Severity.LOW
                    # Enhanced mode gets higher confidence
                    confidence = 0.75 if use_enhanced else 0.6

                    findings.append(
                        Finding(
                            detector=self.name,
                            category="test-coherence",
                            severity=severity,
                            confidence=confidence,
                            title=f"Stale test: {test_name} may not validate {impl_name}",
                            description=(
                                f"Test `{test_name}` in `{test_rel}` may no longer "
                                f"meaningfully validate `{impl_name}` in `{impl_rel}`. "
                                f"Reason: {reason}{gap_text}"
                            ),
                            evidence=[
                                Evidence(
                                    type=EvidenceType.CODE,
                                    content=f"Test: {test_name}\n{test_body[:500]}",
                                    source=test_rel,
                                ),
                                Evidence(
                                    type=EvidenceType.CODE,
                                    content=f"Impl: {impl_name}\n{impl_body[:500]}",
                                    source=impl_rel,
                                ),
                            ],
                            file_path=test_rel,
                            line_start=_find_function_line(test_file, test_name),
                            context={
                                "pattern": "test-code-drift",
                                "test_function": test_name,
                                "impl_function": impl_name,
                                "impl_file": impl_rel,
                                "llm_reason": reason,
                                **({"gaps": gaps} if gaps else {}),
                                **({"enhanced": True} if use_enhanced else {}),
                            },
                        )
                    )

        return findings

    @staticmethod
    def _llm_compare(
        test_name: str,
        test_body: str,
        impl_name: str,
        impl_body: str,
        test_path: str,
        impl_path: str,
        *,
        provider: ModelProvider,
        num_ctx: int = 2048,
        conn: sqlite3.Connection | None = None,
        run_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Ask the LLM whether a test meaningfully validates its implementation."""
        test_text = test_body[:_MAX_TEST_CHARS]
        impl_text = impl_body[:_MAX_IMPL_CHARS]

        prompt = (
            "You are a test quality reviewer. Compare the test function below against "
            "the implementation it is supposed to validate. Determine whether the test "
            "MEANINGFULLY validates the current implementation.\n\n"
            "A test NEEDS REVIEW (flag it) if:\n"
            "- It tests behavior that no longer exists in the implementation\n"
            "- It mocks away the UNIT UNDER TEST's own core logic (not external deps)\n"
            "- The implementation's signature or return type changed but the test wasn't updated\n"
            "- The test only checks trivial properties (e.g., 'not None') while the function "
            "has complex logic that could silently break\n\n"
            "A test is COHERENT (do NOT flag it) if:\n"
            "- It exercises the implementation's actual behavior or key branches\n"
            "- Its assertions validate meaningful properties of the output\n"
            "- Changes to the implementation would cause the test to fail\n"
            "- It uses a CLI test runner (e.g., Click CliRunner.invoke) to test CLI commands — "
            "this IS direct testing of the command function through the framework\n"
            "- It mocks external dependencies (HTTP clients, databases, model APIs) while "
            "testing the code's handling of responses — mocking I/O boundaries is correct\n"
            "- It tests simple methods (serialization, data models, config parsing) with "
            "simple assertions — the assertions match the method's complexity\n"
            "- It checks error handling (exit codes, exceptions, error messages)\n\n"
            f"## Test function: {test_name} (from {test_path})\n"
            f"```python\n{test_text}\n```\n\n"
            f"## Implementation: {impl_name} (from {impl_path})\n"
            f"```python\n{impl_text}\n```\n\n"
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
                "LLM call failed for test-coherence: %s.%s vs %s.%s",
                test_path, test_name, impl_path, impl_name,
                exc_info=True,
            )
            return None

        text = llm_resp.text.strip()
        tokens = llm_resp.token_count or 0
        gen_ms = llm_resp.duration_ms or 0.0
        logger.debug(
            "Test-coherence LLM response (%d tokens): %s", tokens, text[:300],
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
                verdict = "needs_review" if result.get("needs_review") else "coherent"
            from sentinel.store.llm_log import LLMLogEntry, insert_llm_log

            try:
                insert_llm_log(
                    conn,
                    run_id,
                    LLMLogEntry(
                        purpose="test-coherence-comparison",
                        model=getattr(provider, "model", str(provider)),
                        detector="test-coherence",
                        finding_title=f"{test_name} vs {impl_name}",
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
                    "Failed to write test-coherence LLM log entry", exc_info=True,
                )

        return result

    @staticmethod
    def _llm_compare_enhanced(
        test_name: str,
        test_body: str,
        impl_name: str,
        impl_body: str,
        test_path: str,
        impl_path: str,
        *,
        provider: ModelProvider,
        num_ctx: int = 2048,
        conn: sqlite3.Connection | None = None,
        run_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Enhanced comparison using standard+ tier model.

        Returns structured analysis with gaps and severity instead of
        just a binary signal.
        """
        test_text = test_body[:_MAX_TEST_CHARS_ENHANCED]
        impl_text = impl_body[:_MAX_IMPL_CHARS_ENHANCED]

        prompt = (
            "You are a senior test engineer reviewing test quality. Analyze the "
            "test function below against the implementation it validates.\n\n"
            "Evaluate:\n"
            "1. Does the test exercise the implementation's actual behavior?\n"
            "2. Are there important code paths, edge cases, or error conditions "
            "that the test ignores?\n"
            "3. Has the implementation's interface changed in ways the test doesn't "
            "account for?\n"
            "4. Does the test mock away the UNIT UNDER TEST's own core logic? "
            "(Mocking external deps like HTTP, DB, or APIs is correct and should NOT be flagged.)\n"
            "5. Are the assertions testing meaningful properties, not just 'not None'?\n\n"
            "Common COHERENT patterns (do NOT flag):\n"
            "- CLI tests using CliRunner.invoke() or similar framework test tools\n"
            "- Tests that mock HTTP/DB/API responses while testing response handling\n"
            "- Simple tests for simple methods (serialization, config, data models)\n"
            "- Error-handling tests checking exit codes, exceptions, or error messages\n\n"
            f"## Test function: {test_name} (from {test_path})\n"
            f"```python\n{test_text}\n```\n\n"
            f"## Implementation: {impl_name} (from {impl_path})\n"
            f"```python\n{impl_text}\n```\n\n"
            "Respond ONLY with a JSON object (no markdown fences, no explanation "
            "outside JSON):\n"
            "{\n"
            '  "needs_review": true/false,\n'
            '  "severity": "low" | "medium" | "high",\n'
            '  "reason": "One-sentence summary of the main issue (empty if coherent)",\n'
            '  "gaps": ["Description of each specific gap or missing coverage area"]\n'
            "}\n\n"
            "Severity guide:\n"
            "- high: test is fundamentally broken or tests wrong behavior\n"
            "- medium: test misses important paths or has stale assertions\n"
            "- low: minor gaps or style issues, test still catches regressions"
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
                "Enhanced LLM call failed for test-coherence: %s.%s vs %s.%s",
                test_path, test_name, impl_path, impl_name,
                exc_info=True,
            )
            return None

        text = llm_resp.text.strip()
        tokens = llm_resp.token_count or 0
        gen_ms = llm_resp.duration_ms or 0.0
        logger.debug(
            "Test-coherence enhanced LLM response (%d tokens): %s",
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
                verdict = "needs_review" if result.get("needs_review") else "coherent"
            from sentinel.store.llm_log import LLMLogEntry, insert_llm_log

            try:
                insert_llm_log(
                    conn,
                    run_id,
                    LLMLogEntry(
                        purpose="test-coherence-enhanced",
                        model=getattr(provider, "model", str(provider)),
                        detector="test-coherence",
                        finding_title=f"{test_name} vs {impl_name}",
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
                    "Failed to write test-coherence enhanced LLM log entry",
                    exc_info=True,
                )

        return result


# ── Test file discovery ────────────────────────────────────────────


def find_test_files(repo_root: Path) -> list[Path]:
    """Find Python test files in the repository.

    Walks the repo tree, skipping common non-source directories.
    Returns test files sorted by path for deterministic ordering.
    """
    test_files: list[Path] = []

    for py_file in sorted(repo_root.rglob("*.py")):
        try:
            rel = py_file.relative_to(repo_root)
        except ValueError:
            continue

        # Skip common dirs
        if any(part in COMMON_SKIP_DIRS for part in rel.parts):
            continue

        # Skip egg-info dirs
        if any(part.endswith(".egg-info") for part in rel.parts):
            continue

        if _TEST_FILE_RE.match(py_file.name):
            test_files.append(py_file)

    return test_files


def find_implementation_file(test_file: Path, repo_root: Path) -> Path | None:
    """Find the implementation file corresponding to a test file.

    Strategy (in priority order):
    1. Naming convention: test_foo.py → foo.py (search src/ and repo root)
    2. Import analysis: parse the test file's imports to find the most likely target

    Returns the implementation file path, or None if not found.
    """
    impl_name = _impl_name_from_test(test_file.name)
    if impl_name:
        # Search common source directories
        candidates = _find_file_by_name(impl_name, repo_root)
        if candidates:
            return candidates[0]

    # Fall back to import analysis
    return _find_impl_from_imports(test_file, repo_root)


def _impl_name_from_test(test_filename: str) -> str | None:
    """Derive implementation filename from test filename.

    test_config.py → config.py
    config_test.py → config.py
    test_foo_bar.py → foo_bar.py
    """
    name = test_filename
    if name.startswith("test_"):
        return name[5:]  # Remove "test_" prefix
    if name.endswith("_test.py"):
        return name[:-8] + ".py"  # Remove "_test" suffix
    return None


def _find_file_by_name(filename: str, repo_root: Path) -> list[Path]:
    """Search for a file by name in common source locations.

    Prefers src/ directories, then lib/, then repo root.
    Returns up to 3 matches sorted by preference.
    """
    candidates: list[Path] = []
    seen: set[Path] = set()

    # Search priority: src/, lib/, then root
    search_roots = [repo_root / "src", repo_root / "lib", repo_root]

    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for found in sorted(search_root.rglob(filename)):
            if found in seen:
                continue
            seen.add(found)
            try:
                rel = found.relative_to(repo_root)
            except ValueError:
                continue
            if any(part in COMMON_SKIP_DIRS for part in rel.parts):
                continue
            if any(part.endswith(".egg-info") for part in rel.parts):
                continue
            # Skip test files themselves
            if _TEST_FILE_RE.match(found.name):
                continue
            candidates.append(found)
            if len(candidates) >= 3:
                return candidates

    return candidates


def _find_impl_from_imports(test_file: Path, repo_root: Path) -> Path | None:
    """Analyze imports in a test file to find the implementation module.

    Looks for the most common import prefix from the project's own packages
    (not stdlib or third-party).
    """
    try:
        source = test_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    # Collect all imported module paths that look like project-internal
    project_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            # Skip stdlib/third-party (heuristic: project imports typically start
            # with a package name that has a directory in the repo)
            top_level = module.split(".")[0]
            if (repo_root / top_level).is_dir() or (repo_root / "src" / top_level).is_dir():
                project_imports.append(module)

    if not project_imports:
        return None

    # Find the most specific import (longest module path) — usually the impl
    project_imports.sort(key=lambda m: len(m), reverse=True)
    for module_path in project_imports:
        # Convert module path to file path
        parts = module_path.split(".")
        for base in [repo_root / "src", repo_root]:
            candidate = base / "/".join(parts)
            py_file = candidate.with_suffix(".py")
            if py_file.is_file():
                return py_file
            # Check __init__.py for package imports
            init_file = candidate / "__init__.py"
            if init_file.is_file():
                return init_file

    return None


# ── Function-level pairing ─────────────────────────────────────────


def extract_function_pairs(
    test_file: Path, impl_file: Path
) -> list[tuple[str, str, str, str]]:
    """Extract matched (test_func, test_body, impl_func, impl_body) pairs.

    Matches test functions to implementation functions by name:
    test_run_scan → run_scan
    test_build_index_incremental → build_index (prefix match)
    """
    test_funcs = _extract_functions(test_file)
    impl_funcs = _extract_functions(impl_file)

    if not test_funcs or not impl_funcs:
        return []

    # Build lookup of impl function names
    impl_lookup: dict[str, tuple[str, str]] = {}
    for name, body in impl_funcs:
        impl_lookup[name.lower()] = (name, body)

    pairs: list[tuple[str, str, str, str]] = []

    for test_name, test_body in test_funcs:
        # Skip very short test functions
        if test_body.count("\n") < _MIN_FUNC_LINES:
            continue

        impl_name = _match_test_to_impl(test_name, impl_lookup)
        if impl_name is None:
            continue

        impl_real_name, impl_body = impl_lookup[impl_name]
        # Skip short implementations
        if impl_body.count("\n") < _MIN_FUNC_LINES:
            continue

        pairs.append((test_name, test_body, impl_real_name, impl_body))

    return pairs


def _match_test_to_impl(
    test_name: str, impl_lookup: dict[str, tuple[str, str]]
) -> str | None:
    """Match a test function name to an implementation function.

    Matching strategies (in priority order):
    1. Exact strip: test_foo → foo (exact match)
    2. Prefix match: test_foo_bar_baz → foo_bar (longest matching impl prefix)
    """
    # Strip test_ prefix
    if test_name.startswith("test_"):
        base = test_name[5:].lower()
    else:
        return None

    # 1. Exact match
    if base in impl_lookup:
        return base

    # 2. Prefix match — find the longest impl name that is a prefix of `base`
    # Require underscore boundary to avoid spurious matches
    # (e.g. test_run_scan → run_scan, not run)
    best: str | None = None
    best_len = 0
    for impl_key in impl_lookup:
        if base.startswith(impl_key + "_") and len(impl_key) > best_len:
            best = impl_key
            best_len = len(impl_key)

    if best:
        return best

    return None


def _extract_functions(file_path: Path) -> list[tuple[str, str]]:
    """Extract function names and bodies from a Python file.

    Returns list of (function_name, function_body_text) tuples.
    Class methods are included by method name only (without class prefix).
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.split("\n")
    functions: list[tuple[str, str]] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = _get_node_source(node, lines)
            if body:
                functions.append((node.name, body))
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = _get_node_source(child, lines)
                    if body:
                        functions.append((child.name, body))

    return functions


def _get_node_source(node: ast.AST, lines: list[str]) -> str | None:
    """Extract the source text for an AST node."""
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
        return None
    start = node.lineno - 1  # 0-indexed
    end = node.end_lineno  # exclusive
    if start < 0 or end is None or end > len(lines):
        return None
    return "\n".join(lines[start:end])


def _find_function_line(file_path: Path, func_name: str) -> int:
    """Find the line number of a function definition in a file."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node.lineno

    return 1
