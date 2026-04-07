# Phase 5: Cross-Artifact Semantic Detectors

> **Status**: In Progress
> **Prerequisites**: Phase 4 complete, VISION-LOCK v3.0, OQ-008 open
> **Goal**: Build LLM-primary detectors that compare related artifacts (docs vs code, tests vs implementation) for semantic inconsistency — the core differentiator identified in the v3.0 strategic recalibration.

## Key Insight

Even a binary "in sync / needs review" triage signal is high value. The developer doesn't need the LLM to explain *how* the docs are wrong. Identifying *that* something is out of sync is the hard part. A 4B model can deliver that binary signal reliably.

## Acceptance Criteria

1. `semantic-drift` detector compares doc sections against referenced source code and surfaces "needs review" findings
2. Pairing strategy: heading-based doc sections matched to code via name/path references
3. Code extraction: Python `ast` for Python files, regex-based function signatures for other languages
4. LLM prompt is focused and bounded: one doc section + one code excerpt per call
5. Findings include both the doc section and code excerpt as evidence
6. Detector respects `skip_llm` config and degrades gracefully without Ollama
7. False positive rate < 30% on a real project scan
8. Unit tests cover pairing logic, prompt construction, and finding generation

## Implementation Slices

### Slice 1: Semantic Docs-Drift Detector — Core

**Files**: `src/sentinel/detectors/semantic_drift.py`, `tests/detectors/test_semantic_drift.py`

**What**: New detector that:
1. Parses markdown docs into heading-delimited sections
2. Finds file/function references in each section (paths, imports, function names)
3. Reads referenced source files and extracts relevant code (Python: `ast` module for signatures; others: regex)
4. Sends (doc section + code excerpt) to LLM with binary comparison prompt
5. Produces findings for sections flagged as "needs review"

**Approach**:
- Heading chunking: split on `^#{1,3}\s` patterns, keep heading as section title
- Name-based pairing: scan section text for file paths (`src/...`, `*.py`), function names (backtick-wrapped identifiers), and import references
- Python code extraction: use `ast.parse()` to extract function/class signatures with docstrings
- Non-Python code: regex-based extraction of `function`, `def`, `fn`, `func` declarations + first N lines
- LLM prompt: system-level instruction + (doc section ≤500 chars) + (code excerpt ≤1500 chars) → binary JSON response
- Confidence: 0.6 for LLM-sourced findings (lower than deterministic)

**Test**: Unit tests for section parsing, pairing logic, code extraction, mock LLM responses

### Slice 2: Test-Code Coherence Detector (future)

Deferred to next session — depends on OQ-009 resolution and results from Slice 1.

### Slice 3: Real-World Validation

Run semantic-drift on a real project, analyze accuracy, iterate on FP reduction.

## Design Decisions

- **Separate detector, not an extension of docs-drift**: The existing `docs-drift` focuses on broken links and stale references (deterministic + code-block comparison). Semantic drift is fundamentally different — it compares prose descriptions against code behavior. Keeping them separate maintains clean separation of concerns.
- **No tree-sitter dependency for v1**: Python's `ast` module handles Python files well. Regex handles common patterns in other languages. Tree-sitter can be added later for more precise extraction.
- **Heading-based chunking over sentence-level**: Headings are natural boundaries in documentation. Sentence-level chunking requires NLP and produces too many LLM calls.
- **Binary output format**: "needs_review" / "in_sync" — not requiring the LLM to explain *what* is wrong, just *whether* it is wrong. This is more reliable at 4B.

## Open Questions Addressed

- **OQ-008**: Pairing strategy is heading-based chunking + name-matching. Start simple, expand to embedding-based pairing if needed.
