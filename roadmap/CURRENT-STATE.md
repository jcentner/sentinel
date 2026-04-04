# Current State — Sentinel

> Last updated: 2026-04-04 (Session 3)

## Session 3 Summary

### Current Objective
Complete Phase 2 (Docs-Drift Detector), update README, and begin Phase 3 refinement.

### What Was Accomplished
1. **Verified baseline**: 129 tests passing, lint clean, `sentinel scan .` working
2. **Updated README**: Installation/usage instructions, status updated from "pre-development"
3. **Marked Phase 1 complete** in roadmap
4. **Created Phase 2 plan**: 6 implementation slices for docs-drift detector
5. **Implemented all Phase 2 slices**:
   - Stale reference detection (broken markdown links, missing inline code paths)
   - Dependency drift detection (README install commands vs pyproject.toml/requirements.txt/package.json)
   - LLM-assisted doc-code comparison (compares doc code blocks against actual source)
   - Repo-root relative link resolution (reduces false positives)
   - Template/example path filtering (reduces false positives)
   - Integration tests for docs-drift in the full pipeline
6. **Self-scan validation**: Reduced from 17 to 1 docs-drift finding on own repo
7. **165 tests** all passing, ruff lint clean

### Repository State
- **Phase 0 (Foundation)**: Complete
- **Phase 1 (MVP Core)**: Complete — 3 detectors, LLM judge, SQLite state, morning report
- **Phase 2 (Docs-Drift)**: **Complete** — docs-drift detector with 3 detection patterns
- **Implementation code**: 13 Python modules in `src/sentinel/`
- **Test code**: 12 test files, 165 tests
- **Vision lock**: Created, baselined (Session 1), one revision (VISION-REVISION-001)
- **Open questions**: 4 open (OQ-002, OQ-004, OQ-005, OQ-006), 3 resolved
- **ADRs**: 8 accepted
- **Lint**: Clean (ruff)
- **Detectors**: todo-scanner, lint-runner, dep-audit, docs-drift

### Test Results
```
165 passed in 2.95s
ruff check: All checks passed
```

### Decisions Made This Session
1. Docs-drift link resolution: try both doc-relative and repo-root-relative (common GitHub pattern)
2. Template path filtering: skip paths with placeholder words (path/to/) and variable patterns (-N-)
3. Tier classification: docs-drift is `llm-assisted` tier (has both deterministic and LLM patterns)
4. Runner passes Ollama config to detectors via DetectorContext.config dict
5. Doc-code comparison confidence: 0.65 (lower than deterministic patterns at 0.80-0.95)

### What Remains / Next Priority
**Phase 3: Refinement** — next steps:
1. FP tuning: review todo-scanner results on test data strings in test files
2. Finding persistence scoring (recurring = higher confidence)
3. Report format improvements
4. Incremental run optimization
5. Consider Phase 4 detectors (git-hotspots, semgrep)

### Blocked Items
None.

### Files Created This Session
- `roadmap/phases/phase-2-docs-drift.md` — Phase 2 implementation plan
- `src/sentinel/detectors/docs_drift.py` — docs-drift detector (stale refs, dep drift, LLM comparison)
- `tests/detectors/test_docs_drift.py` — 34 tests for docs-drift detector

### Files Modified This Session
- `README.md` — updated with installation, usage, status
- `roadmap/README.md` — Phase 1 complete, Phase 2 complete, Phase 3 in progress
- `src/sentinel/core/runner.py` — added docs_drift import, pass Ollama config to DetectorContext
- `tests/test_integration.py` — added docs-drift integration tests

## Session 2 Summary (Previous)
- Implemented all 15 Phase 1 MVP slices
- 126 tests, ruff clean
- Full pipeline: 3 detectors → fingerprint → dedup → context → judge → report
- CLI: scan, suppress, approve, history commands

## Session 1 Summary (Previous)
- Created VISION-LOCK.md, CURRENT-STATE.md, agent-improvement-log.md
- Created ADR-008, resolved OQ-007
- Created Phase 1 plan with 15 slices
- Phase 0 complete
