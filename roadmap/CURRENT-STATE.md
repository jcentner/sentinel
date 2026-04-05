# Current State — Sentinel

> Last updated: 2026-04-05 (Session 5)

## Session 5 Summary

### Current Objective
Complete Phase 3 (Refinement): schema migration system, finding persistence scoring, report improvements.

### What Was Accomplished

**Turn 1 — Schema migration system (TD-003):**
1. Refactored `store/db.py` with a proper migration framework: base v1 schema + ordered migration tuples
2. Migrations are `(version, description, sql)` tuples applied sequentially on DB open
3. Added migration v2: `finding_persistence` table for tracking occurrence counts
4. TD-003 resolved

**Turn 1 — Finding persistence scoring:**
5. Created `store/persistence.py` with `update_persistence()` and `get_persistence_info()`
6. `finding_persistence` table: fingerprint (PK), first_seen, last_seen, occurrence_count
7. Uses `ON CONFLICT DO UPDATE` for atomic upsert
8. Pipeline runner now calls `update_persistence` after storing findings
9. Findings get `occurrence_count`, `first_seen`, and `recurring` annotations in context

**Turn 1 — Report improvements:**
10. Badge format: `♻️ ×3` shows exact occurrence count for recurring findings
11. Summary section: New vs Recurring breakdown driven by occurrence_count data
12. Consolidated badge logic (recurring + FP verdict) into cleaner format
13. Updated report test to use occurrence_count convention

**Turn 1 — Testing:**
14. 8 new tests: migration from v1, persistence CRUD, batch operations, timestamps
15. 190 tests pass (was 182), lint clean

### Repository State
- **Phase 0 (Foundation)**: Complete
- **Phase 1 (MVP Core)**: Complete
- **Phase 2 (Docs-Drift)**: Complete
- **Phase 3 (Refinement)**: Complete — persistence scoring, migration system, report improvements
- **Implementation code**: 16 Python modules in `src/sentinel/`
- **Test code**: 13 test files, 190 tests (including 8 persistence/migration tests)
- **Detectors**: todo-scanner, lint-runner, dep-audit, docs-drift
- **CLI commands**: scan, eval, suppress, approve, history
- **Vision lock**: Baselined (Session 1), one revision
- **DB schema**: v2 (migration framework with finding_persistence table)
- **Open questions**: 4 open (OQ-002, OQ-004, OQ-005, OQ-006), 3 resolved
- **ADRs**: 8 accepted
- **Tech debt**: 5 active (TD-001, TD-002, TD-004, TD-005, TD-008), 3 resolved (TD-003, TD-006, TD-007)
- **Lint**: Clean (ruff)

### Test Results
```
190 passed in 12.10s
ruff check: All checks passed
```

### Decisions Made This Session
1. Migration framework: ordered tuples `(version, description, sql)` applied sequentially — simplest possible approach
2. Finding persistence uses `ON CONFLICT DO UPDATE` upsert for atomic occurrence counting
3. Occurrence count shown as explicit badge `♻️ ×N` rather than just a flag

### What Remains / Next Priority
**Phase 4 (Extended Detectors):**
1. Git-hotspots detector (high churn files = review attention) — next priority
2. Semgrep integration detector
3. Complexity/dead-code heuristics

**Phase 5 (GitHub Integration):**
4. GitHub issue creation from approved findings
5. Approval workflow
6. Issue dedup against existing GitHub issues

**Remaining tech debt:**
7. TD-001: Context gatherer upgrade to embedding-based (needs OQ-004 resolution)
8. TD-002: Async detector interface (not blocking)
9. TD-004: Config type validation (low priority)
10. TD-005: TODO comments in markdown invisible (low priority)
11. TD-008: Poetry pyproject.toml format (low priority)

**Deferred:**
12. Incremental run optimization (Phase 3 item — scan only changed files)
13. Multi-repo support (OQ-005)

### Blocked Items
None currently.

### Files Created This Session
- `src/sentinel/store/persistence.py` — finding persistence tracking module

### Files Modified This Session
- `src/sentinel/store/db.py` — migration framework + v2 migration
- `src/sentinel/core/runner.py` — persistence tracking in pipeline
- `src/sentinel/core/report.py` — occurrence count badges, data-driven recurring counts
- `tests/test_store.py` — 8 new tests (migration, persistence)
- `tests/test_report.py` — updated recurring marker test
- `docs/reference/tech-debt.md` — TD-003 resolved
- `roadmap/README.md` — Phase 3 status updated
- `src/sentinel/config.py` — default model
- `pyproject.toml` — ruff exclude for fixtures
- `docs/reference/tech-debt.md` — TD-006/007 resolved, TD-008 added
- `tests/test_eval.py` — refactored to use shared ground truth
- `tests/test_store.py` — timestamp round-trip test
- `tests/detectors/test_dep_audit.py` — pyproject deps tests

## Session 3 Summary (Previous)
- Phase 2 (Docs-Drift) complete: stale refs, dep drift, LLM doc-code comparison
- Phase 3 refinements: TODO FP reduction, report fingerprint IDs
- 170 tests, lint clean

## Session 2 Summary (Previous)
- Implemented all 15 Phase 1 MVP slices
- 126 tests, ruff clean
- Full pipeline: 3 detectors → fingerprint → dedup → context → judge → report

## Session 1 Summary (Previous)
- Created VISION-LOCK.md, CURRENT-STATE.md, agent-improvement-log.md
- Created ADR-008, resolved OQ-007
- Created Phase 1 plan with 15 slices
- Phase 0 complete
