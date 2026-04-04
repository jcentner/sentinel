# Current State — Sentinel

> Last updated: 2026-04-04 (Session 3)

## Session 3 Summary

### Current Objective
Complete Phase 2 (Docs-Drift Detector) and Phase 3 refinements (FP reduction, report UX).

### What Was Accomplished
**Phase 1 completion:**
1. Verified baseline: 129 tests passing, lint clean
2. Updated README with full installation/usage instructions
3. Self-scan validated: `sentinel scan .` working end-to-end

**Phase 2 (Docs-Drift Detector) — ALL SLICES COMPLETE:**
4. Stale reference detection (broken markdown links, missing inline code paths)
5. Dependency drift detection (README install commands vs pyproject.toml/requirements.txt/package.json)
6. LLM-assisted doc-code comparison (code blocks vs actual source, via Ollama)
7. Repo-root relative link resolution + template path filtering (FP reduction)
8. Integration tests for docs-drift in full pipeline
9. Self-scan validation: 17 → 1 docs-drift finding

**Phase 3 (Refinement) — KEY IMPROVEMENTS:**
10. TODO scanner: string literal detection (skip TODOs inside Python strings)
11. TODO scanner: skip markdown/docs files (docs-drift handles docs)
12. TODO scanner: proximity check (require TODO near comment prefix, skip mid-sentence mentions)
13. Report UX: show finding fingerprint IDs for suppress/approve commands
14. Self-scan: from 27 total findings down to 2 (both borderline-reasonable)

### Repository State
- **Phase 0 (Foundation)**: Complete
- **Phase 1 (MVP Core)**: Complete
- **Phase 2 (Docs-Drift)**: Complete
- **Phase 3 (Refinement)**: In progress — FP tuning done, more possible
- **Implementation code**: 13 Python modules in `src/sentinel/`
- **Test code**: 12 test files, 170 tests
- **Detectors**: todo-scanner, lint-runner, dep-audit, docs-drift
- **Vision lock**: Baselined (Session 1), one revision
- **Open questions**: 4 open (OQ-002, OQ-004, OQ-005, OQ-006), 3 resolved
- **ADRs**: 8 accepted
- **Lint**: Clean (ruff)

### Test Results
```
170 passed in 3.07s
ruff check: All checks passed
Self-scan: 2 findings (1 borderline docs-drift, 1 borderline todo)
```

### Decisions Made This Session
1. Docs-drift: try both doc-relative and repo-root-relative link resolution
2. Template path filtering: skip paths with placeholder words and variable patterns
3. Docs-drift tier: `llm-assisted` (both deterministic and LLM patterns)
4. Runner passes Ollama config to detectors via DetectorContext.config dict
5. Doc-code comparison confidence: 0.65 (lower than deterministic at 0.80-0.95)
6. TODO scanner: skip .md/.rst/.adoc files (docs-drift handles docs)
7. TODO scanner: require TODO within 5 chars of comment prefix
8. Report: show fingerprint IDs for suppress/approve workflow

### What Remains / Next Priority
**Phase 3 continued / Phase 4 planning:**
1. Finding persistence scoring (recurring findings gain confidence) — deferred
2. Incremental run optimization (only scan changed files) — deferred
3. Consider git-hotspots detector (Phase 4)
4. Consider Semgrep integration (Phase 4)
5. GitHub issue creation workflow (Phase 5)

### Blocked Items
- pip-audit not installed in venv (dep-audit detector skipped during self-scan)
  - Not blocking: `pip install pip-audit` resolves it, but requires network access

### Files Created This Session
- `roadmap/phases/phase-2-docs-drift.md` — Phase 2 implementation plan
- `src/sentinel/detectors/docs_drift.py` — docs-drift detector
- `tests/detectors/test_docs_drift.py` — 34 tests for docs-drift

### Files Modified This Session
- `README.md` — installation, usage, status update
- `roadmap/README.md` — Phase status updates  
- `src/sentinel/core/runner.py` — docs_drift import, Ollama config passing
- `src/sentinel/core/report.py` — fingerprint IDs in report
- `src/sentinel/detectors/todo_scanner.py` — FP reduction (string literals, proximity, skip docs)
- `tests/test_integration.py` — docs-drift integration tests
- `tests/test_report.py` — fingerprint display test
- `tests/detectors/test_todo_scanner.py` — new FP test cases

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
