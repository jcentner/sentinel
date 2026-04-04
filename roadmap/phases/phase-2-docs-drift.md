# Phase 2: Docs-Drift Detector — Implementation Plan

> **Status**: Complete
> **Prerequisites**: Phase 1 complete (all 15 MVP slices done, 129 tests passing)
> **Goal**: A docs-drift detector that surfaces stale references, dependency drift, and semantic documentation inconsistencies as first-class findings.

## Background

ADR-005 establishes docs-drift as a first-class detector category. Documentation inconsistency is common, hard to catch with existing linters, and a natural fit for the deterministic + LLM comparison approach.

## Acceptance Criteria

1. `sentinel scan` includes the docs-drift detector automatically
2. Stale references (docs mentioning non-existent files/paths) are detected with high confidence
3. Dependency drift (README install instructions vs actual project dependencies) is detected
4. Code block drift (documented CLI commands/API that no longer match reality) is detected when LLM is available
5. All docs-drift findings include concrete evidence showing the doc claim and the reality
6. Deterministic patterns (stale refs, dep drift) work without Ollama
7. LLM-assisted patterns degrade gracefully when Ollama is unavailable
8. Detector has TP and FP test cases
9. False positive rate for deterministic patterns is near zero

## Implementation Slices

### Slice 1: Docs-Drift Detector Skeleton
**Files**: `src/sentinel/detectors/docs_drift.py`, `tests/detectors/test_docs_drift.py`
**What**: Create the detector class implementing the Detector ABC. Register it in the detector system. Parse markdown files to extract structured elements: file references (links), code blocks, heading structure.
**Test**: Detector registers, produces empty findings on a repo with no docs.
**Commit**: `feat(detector): add docs-drift detector skeleton with markdown parser`

### Slice 2: Stale Reference Detection
**Files**: `src/sentinel/detectors/docs_drift.py`, `tests/detectors/test_docs_drift.py`
**What**: Detect references in markdown files that point to non-existent files. Covers:
- `[text](path/to/file.md)` markdown links
- `[text](path/to/file.md#section)` section links (check file exists, section check is optional)
- Explicit path mentions in prose (e.g., `See \`src/foo.py\``)
- File paths in code blocks that look like relative paths
Confidence: 95% for direct link references, 80% for inline path mentions.
**Test**: True positives (dead links, missing files), false positives (URLs, anchors, glob patterns).
**Commit**: `feat(detector): implement stale reference detection in docs-drift`

### Slice 3: Dependency Drift Detection
**Files**: `src/sentinel/detectors/docs_drift.py`, `tests/detectors/test_docs_drift.py`
**What**: Compare install instructions in README/CONTRIBUTING against actual project definition files:
- Parse `pip install` commands in README code blocks → extract package names
- Parse `pyproject.toml` / `setup.py` / `requirements.txt` → extract declared dependencies
- Parse `npm install` / `package.json` → extract declared dependencies
- Flag: packages mentioned in README install but not in dependency files (or vice versa)
Confidence: 90% for clear mismatches.
**Test**: True positives (README mentions dep not in pyproject.toml), false negative resilience, false positives (dev deps, optional deps).
**Commit**: `feat(detector): implement dependency drift detection`

### Slice 4: LLM-Assisted Doc-Code Comparison
**Files**: `src/sentinel/detectors/docs_drift.py`, `tests/detectors/test_docs_drift.py`
**What**: For each README/doc code block that describes usage (CLI commands, API examples, config snippets), gather the corresponding source code and ask the LLM judge: "Does this documentation accurately describe this code?" Reuses the existing Ollama judge infrastructure. Lower confidence (0.6–0.8), flagged for human review. Gracefully skipped when Ollama is unavailable.
**Test**: Mocked LLM responses for accurate/inaccurate doc-code pairs.
**Commit**: `feat(detector): add LLM-assisted doc-code comparison`

### Slice 5: Integration and Runner Registration
**Files**: `src/sentinel/core/runner.py`, `tests/test_integration.py`
**What**: Register docs-drift detector in the runner's `_ensure_detectors_loaded()`. Add integration test with a test repo containing stale references and dependency drift. Verify findings appear in the morning report correctly.
**Test**: E2E test with docs-drift findings in the report.
**Commit**: `feat(detector): integrate docs-drift detector into pipeline`

### Slice 6: Self-Scan Validation
**What**: Run `sentinel scan .` on the Sentinel repo itself and verify docs-drift findings are legitimate (if any). Fix any false positives revealed. Update docs if drift is found.
**Commit**: `test(detector): validate docs-drift on Sentinel's own repo`

## Dependencies

- Existing detector framework (base.py, registry)
- Existing models (Finding, Evidence, EvidenceType)
- Existing runner pipeline
- Existing LLM judge infrastructure (for Slice 4)
- No new external dependencies required (markdown parsing uses regex + stdlib)

## Risks

1. **Markdown link extraction regex**: May miss edge cases. Mitigation: keep patterns simple, add FP tests.
2. **Dependency name normalization**: pip/npm package names have different normalization rules. Mitigation: normalize to lowercase, strip version specifiers.
3. **LLM accuracy on doc-code comparison**: Small models may not reliably judge semantic drift. Mitigation: flag as low-confidence, require human review.
4. **Prose path detection false positives**: Text that looks like paths but isn't. Mitigation: require path to start from a known project directory prefix or use backtick markers.
