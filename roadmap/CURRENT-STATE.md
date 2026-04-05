# Current State — Sentinel

> Last updated: 2026-04-05 (Session 6 — real-world test evaluation)

## Session 6 Summary

### Current Objective
Evaluate report from real-world test run on agent-realtor repo and refine detectors based on findings.

### What Was Accomplished

**Real-world report evaluation (396 findings, 14,555 lines):**
1. Analyzed Sentinel report generated from a real TypeScript/Node.js repo (agent-realtor)
2. Identified three major noise sources causing the report to fail the "scannable in 2 minutes" vision criterion

**Fix 1 — Docs-drift absolute path FP elimination:**
3. Inline path checker now skips absolute paths (`/hooks/...`, `/app/skills/`, `/health`)
4. These paths describe external systems (Docker containers, remote servers), not repo files
5. Estimated ~200+ false positive LOW findings eliminated per scan on repos with infrastructure docs

**Fix 2 — Git-hotspots documentation noise reduction:**
6. Documentation files (.md, .rst, .txt, .adoc) now capped at confidence ≤0.30 and severity LOW
7. High churn on docs is expected behavior (the judge was correctly marking most as FP)
8. Code files retain normal confidence/severity escalation

**Fix 3 — Report LOW truncation + detector summary:**
9. LOW findings now truncated to 20 (configurable via `_MAX_LOW_FINDINGS`)
10. Per-detector count breakdown added to summary section
11. MEDIUM+ findings always shown in full — no truncation

**Tests:**
12. 7 new tests: absolute path skip, doc file severity cap, doc confidence cap, code file normal, LOW truncation, MEDIUM not truncated, detector breakdown
13. All 234 tests pass, ruff lint clean

### Decisions Made This Session
1. Absolute paths cannot be repo-relative, so they should never trigger stale-path findings
2. Doc file churn threshold: 0.30 confidence cap — matches the judge's own FP self-flagging behavior
3. LOW cap at 20 — enough to show patterns without overwhelming the report. Higher severities always shown in full.

### Observations from the Real-World Run
- The 31 MEDIUM docs-drift findings (stale links) were **all true positives** — files moved to `archive/` but links not updated
- The 3 MEDIUM git-hotspot findings were reasonable — especially the 1229-line code file with 26 commits
- Most LOW findings were noise — absolute path references to external systems, doc file churn
- The LLM judge was correctly identifying FPs but the findings were still cluttering the report
- Only 2 of 5 detectors fired (docs-drift, git-hotspots). todo-scanner, lint-runner, dep-audit found nothing, which is plausible for that repo type
- Grouping related findings (15+ stale links from same root cause) would further reduce noise — deferred as future work

## Previous Sessions

### Session 5 Summary

### Current Objective
Complete Phase 3 (Refinement), advance Phase 4 (Extended Detectors), complete Phase 5 (GitHub Integration).

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

**Turn 2 — Git-hotspots detector (Phase 4):**
13. New detector: `git-hotspots` identifies files with unusually high commit frequency
14. Statistical approach: flags files with commits above (mean + N*stdev) threshold
15. Configurable: lookback period, min commits, stdev threshold
16. Reports commit count, distinct authors, file size in evidence
17. 12 tests including real git repo E2E tests

**Turn 3 — GitHub issue creation (Phase 5):**
18. New module `src/sentinel/github.py`: `create_issues()`, `get_approved_findings()`
19. `GitHubConfig` from CLI args or `SENTINEL_GITHUB_*` env vars
20. Dedup against existing open issues via fingerprint markers in issue body
21. Dry-run mode for previewing without API calls
22. New CLI command `sentinel create-issues` with --dry-run, --owner, --github-repo, --token
23. Approve command now hints about create-issues
24. 15 tests covering config, formatting, dedup, dry run, mocked API creation

### Repository State
- **Phase 0 (Foundation)**: Complete
- **Phase 1 (MVP Core)**: Complete
- **Phase 2 (Docs-Drift)**: Complete
- **Phase 3 (Refinement)**: Complete — persistence scoring, migration system, report improvements
- **Phase 4 (Extended Detectors)**: In progress — git-hotspots done, others deferred
- **Phase 5 (GitHub Integration)**: Complete — issue creation, dedup, dry-run, approval workflow
- **Implementation code**: 18 Python modules in `src/sentinel/`
- **Test code**: 15 test files, 217 tests
- **Detectors**: todo-scanner, lint-runner, dep-audit, docs-drift, git-hotspots
- **CLI commands**: scan, eval, suppress, approve, history, create-issues
- **DB schema**: v2 (migration framework with finding_persistence table)
- **Open questions**: 4 open (OQ-002, OQ-004, OQ-005, OQ-006), 3 resolved
- **ADRs**: 8 accepted
- **Tech debt**: 5 active (TD-001, TD-002, TD-004, TD-005, TD-008), 3 resolved (TD-003, TD-006, TD-007)
- **Lint**: Clean (ruff)

### Test Results
```
217 passed in 13.14s
ruff check: All checks passed
```

### Decisions Made This Session
1. Migration framework: ordered tuples `(version, description, sql)` applied sequentially — simplest possible approach
2. Finding persistence uses `ON CONFLICT DO UPDATE` upsert for atomic occurrence counting
3. Occurrence count shown as explicit badge `♻️ ×N` rather than just a flag
4. Git-hotspots: statistical threshold (mean + N*stdev) with configurable parameters
5. GitHub issue creation: fingerprint markers in issue body (`<!-- sentinel:fingerprint:xxx -->`) for dedup
6. GitHub: env vars `SENTINEL_GITHUB_*` as primary config mechanism, CLI flags as overrides

### Vision Success Criteria Status
All seven success criteria from VISION-LOCK are satisfied:
1. ✅ Install, point at repo, run scan → useful morning report
2. ✅ Report scannable in < 2 minutes (one-line per finding, collapsible evidence)
3. ✅ FP rate acceptable (93%+ precision on ground truth)
4. ✅ Findings deduplicated across runs (fingerprinting + SQLite dedup)
5. ✅ Works fully offline except optional GitHub issue creation
6. ✅ Swap LLM model = config change only
7. ✅ Suppress a FP and it stays suppressed

### What Remains / Next Priority
**Remaining Phase 4 detectors (deferred — not blocking MVP):**
1. SQL anti-pattern detection (depends on OQ-006 resolution)
2. Semgrep integration
3. Complexity/dead-code heuristics

**Remaining tech debt:**
4. TD-001: Context gatherer upgrade to embedding-based (needs OQ-004 resolution)
5. TD-002: Async detector interface (not blocking)
6. TD-004: Config type validation (low priority)
7. TD-005: TODO comments in markdown invisible (low priority)
8. TD-008: Poetry pyproject.toml format (low priority)

**Future enhancements:**
9. Incremental run optimization (scan only changed files)
10. Multi-repo support (OQ-005)
11. Web UI for report review and approval (OQ-002)
12. GitHub issue rate limiting and error handling
13. Custom detector plugin system

### Blocked Items
None currently.

### Files Created This Session
- `src/sentinel/store/persistence.py` — finding persistence tracking module
- `src/sentinel/detectors/git_hotspots.py` — git churn hotspot detector
- `tests/detectors/test_git_hotspots.py` — 12 tests for git-hotspots
- `src/sentinel/github.py` — GitHub issue creation module
- `tests/test_github.py` — 15 tests for GitHub integration

### Files Modified This Session
- `src/sentinel/store/db.py` — migration framework + v2 migration
- `src/sentinel/core/runner.py` — persistence tracking + git-hotspots registration
- `src/sentinel/core/report.py` — occurrence count badges, data-driven recurring counts
- `src/sentinel/cli.py` — create-issues command, approve hint
- `tests/test_store.py` — 8 new tests (migration, persistence)
- `tests/test_report.py` — updated recurring marker test
- `docs/reference/tech-debt.md` — TD-003 resolved
- `roadmap/README.md` — Phase 3/4/5 status updated
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
