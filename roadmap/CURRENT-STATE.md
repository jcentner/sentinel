# Current State — Sentinel

> Last updated: 2026-04-05 (Session 10 — docs alignment, mypy, targeted scan, self-validation)

## Session 10 Summary

### Current Objective
Docs-code alignment, mypy type safety, expose targeted scan, validate via self-scan.

### What Was Accomplished

**Docs-code alignment fixes (critical):**
1. Architecture overview: trigger modes now accurately describe Manual as the only implemented trigger; cron/systemd documented as external user-configured tools
2. Architecture overview: scope section corrected — Full scan is the default, not incremental
3. Architecture overview: replaced internal "Session 9" reference with date

**README completeness:**
4. Added `--embed-model` and `--target` to scan options table
5. Added all 3 embed config keys to sentinel.toml example
6. Added `--repo` context to suppress/approve examples
7. Added `--ground-truth` to eval example
8. Added scheduling section with cron and systemd timer examples
9. Added targeted scan usage example
10. Noted `-v, --verbose` is a global flag placed before subcommands
11. Fixed cron redirect order (was `2>&1 >>`, now `>> 2>&1`)
12. Added `mypy` to development commands

**Detector interface alignment:**
13. Moved `test-runner` from "Planned (MVP)" to "Planned (Phase 2+)"
14. Updated status line from "Session 8" to date format

**New feature: `--target` CLI flag:**
15. Added `--target, -t` option (repeatable) to `sentinel scan` command
16. Sets ScopeType.TARGETED and passes target_paths to run_scan()
17. Errors if combined with `--incremental`
18. Test verifies scope and target_paths propagate to detector context

**mypy type safety (37 → 0 errors):**
19. Added `dict[str, Any]` generic type args to 17 bare dict annotations across 14 files
20. Fixed None-safety with asserts in context.py, runner.py, cli.py, dep_audit.py
21. Fixed `no-any-return` in judge.py, embeddings.py, docs_drift.py, ollama.py
22. Added `ignore_missing_imports` to pyproject.toml mypy config

**Self-scan validation:**
23. Ran `sentinel scan /home/jakce/sentinel --skip-judge` successfully
24. 45 findings: 22 docs-drift, 5 git-hotspots, 2 lint, 17 TODOs
25. HIGH findings are real (sample-repo test fixtures with intentional issues)
26. Some LOW docs-drift FPs on inline path references in prose — acceptable, known pattern

### Decisions Made This Session
1. No built-in scheduler — cron/systemd timer documented in README
2. `test-runner` detector deferred to Phase 2+
3. Targeted scan paths not validated as click.Path — detectors handle gracefully
4. dep-audit and git-hotspots are inherently repo-scoped, don't filter by target_paths
5. mypy strict mode with ignore_missing_imports — zero errors is the baseline going forward

### Test Results
```
317 passed in 18.02s
ruff check: All checks passed
mypy: Success: no issues found in 29 source files
```

### Repository State
- **Phases**: 0–3 and 5 complete, Phase 4 in progress (git-hotspots done)
- **Implementation**: 21 Python modules in `src/sentinel/`
- **Tests**: 19 test files, 317 tests
- **Detectors**: todo-scanner (with markdown HTML comments), lint-runner, dep-audit, docs-drift (with Poetry), git-hotspots
- **CLI**: scan (with --incremental, --embed-model, --target), eval, suppress, approve, history, create-issues, index
- **DB schema**: v5 (migration framework, finding persistence, llm_log, commit_sha, chunks + embed_meta)
- **Open questions**: 2 open (OQ-005, OQ-006), 5 resolved
- **ADRs**: 9 accepted
- **Tech debt**: 1 active (TD-002 async), 7 resolved
- **Lint**: Clean (ruff)
- **Type check**: Clean (mypy strict)
- **Ground truth**: 15 expected TPs in eval fixture
- **Self-scan**: Validated — 45 findings, report well-structured
- **Docs**: All aligned with actual implementation

### What Remains / Next Priority
1. TD-002: Async detector interface (low priority)
2. Phase 4 remaining detectors: SQL anti-patterns, Semgrep, complexity/dead-code, test-runner (deferred)
3. Multi-repo support (OQ-005)
4. Custom detector plugin system
5. Finding grouping by root cause (deeper than directory clustering)
6. Web UI for report review (future)
7. Docs-drift FP reduction: inline path references in prose trigger false stale-path findings

### Blocked Items
None.

### Vision Completion Status
All 7 MVP success criteria are met:
1. ✅ Developer can install, scan, and get a useful morning report
2. ✅ Report scannable in <2 minutes (one line per finding, expandable evidence, severity tags)
3. ✅ FP rate subjectively acceptable (93% precision on ground truth)
4. ✅ Findings deduplicated across runs
5. ✅ Works fully offline (except optional GitHub issue creation)
6. ✅ Swapping the LLM model requires changing configuration, not code
7. ✅ User can suppress a false positive and it stays suppressed

## Previous Sessions

### Session 9 Summary (embedding-based context gatherer)
- Implemented embedding-based semantic context (ADR-009, TD-001 resolved, OQ-004 resolved)
- `embed_texts()`, `store/embeddings.py`, `core/indexer.py`, `core/context.py` upgraded
- Schema v5: chunks + embed_meta tables
- New `sentinel index` CLI command, `--embed-model` on scan
- 35 new tests (316 total)
- Decisions: no sqlite-vec, nomic-embed-text default, opt-in only, incremental re-indexing

## Session 8 Summary

### Current Objective
Reduce morning report noise via finding clustering, resolve remaining low-severity tech debt.

### What Was Accomplished

**Finding clustering (report noise reduction):**
1. New module `src/sentinel/core/clustering.py` with `FindingCluster` dataclass and `cluster_findings()` function
2. Groups findings by parent directory within each severity/category bucket
3. Clusters of 3+ findings collapse into a `<details>` block in the morning report
4. Collapsed clusters count as 1 item toward LOW truncation cap
5. 18 new tests (unit + report integration)

**Markdown HTML comment TODOs (TD-005 resolved):**
6. New `_scan_markdown_todos()` method in the TODO scanner
7. Detects `<!-- TODO/FIXME/HACK/XXX: ... -->` patterns in `.md`, `.rst`, `.adoc`, `.html` files
8. Fixed `_get_files()` to apply `_SKIP_EXTENSIONS` filter in incremental/targeted modes (pre-existing bug)
9. 6 new tests for markdown TODO detection
10. Updated sample-repo ground truth: 2 new HTML comment TODO entries (15 TPs total)

**Poetry pyproject.toml support (TD-008 resolved):**
11. `_parse_pyproject_deps()` now reads `[tool.poetry.dependencies]` and `[tool.poetry.group.*.dependencies]`
12. Python version entries excluded automatically
13. 4 new tests for Poetry format

**Docs-code alignment (major docs update):**
14. Rewrote `docs/architecture/overview.md` — corrected pipeline diagram, removed aspirational embeddings claims, updated schema version, added clustering/persistence/fingerprinting as explicit pipeline steps
15. Updated `docs/architecture/detector-interface.md` — renamed `id` to `fingerprint`, added `status` field, fixed `previous_run` note
16. Fixed `roadmap/README.md` — corrected stale phase labels, marked incremental as complete
17. Added 6 new glossary terms: clustering, FindingCluster, targeted scan, ground truth, evaluation, migration framework

### Decisions Made This Session
1. Clustering is purely a report-layer feature — no model changes or pipeline modifications needed
2. Cluster minimum size is 3 (below that, show individually) — balances grouping vs. hiding
3. Collapsed clusters count as 1 visible item toward LOW truncation cap (a cluster is a single scannable element)
4. Markdown TODO scanning is a separate pass from code scanning — keeps the code scanner's FP prevention intact
5. `_get_files()` in targeted/incremental mode should respect `_SKIP_EXTENSIONS` (bug fix)

### Test Results
```
281 passed in 16.66s
ruff check: All checks passed
```

### Repository State
- **Phases**: 0–3 and 5 complete, Phase 4 in progress (git-hotspots done)
- **Implementation**: 19 Python modules in `src/sentinel/`
- **Tests**: 18 test files, 281 tests
- **Detectors**: todo-scanner (with markdown HTML comments), lint-runner, dep-audit, docs-drift (with Poetry), git-hotspots
- **CLI**: scan (with --incremental), eval, suppress, approve, history, create-issues
- **DB schema**: v4 (migration framework, finding persistence, llm_log, commit_sha)
- **Open questions**: 4 open (OQ-002, OQ-004, OQ-005, OQ-006), 3 resolved
- **ADRs**: 8 accepted
- **Tech debt**: 2 active (TD-001, TD-002), 6 resolved
- **Lint**: Clean (ruff)
- **Ground truth**: 15 expected TPs in eval fixture
- **Docs**: Architecture overview, detector interface, roadmap, and glossary all aligned with actual implementation

### What Remains / Next Priority
1. TD-001: Context gatherer upgrade to embedding-based (needs OQ-004 resolution)
2. TD-002: Async detector interface (low priority)
3. Phase 4 remaining detectors: SQL anti-patterns, Semgrep, complexity/dead-code
4. Multi-repo support (OQ-005)
5. Finding grouping by root cause (e.g., same moved directory) — deeper than directory clustering
6. Custom detector plugin system
7. Watch mode / cron trigger

### Blocked Items
None.

### Files Created This Session
- `src/sentinel/core/clustering.py` — finding clustering module
- `tests/test_clustering.py` — 18 clustering tests

### Files Modified This Session
- `src/sentinel/core/report.py` — integrated clustering, added `_format_cluster()`
- `src/sentinel/detectors/todo_scanner.py` — `_scan_markdown_todos()`, `_get_markdown_files()`, `_SKIP_EXTENSIONS` fix
- `src/sentinel/detectors/docs_drift.py` — Poetry format in `_parse_pyproject_deps()`
- `tests/test_report.py` — updated LOW truncation test for clustering
- `tests/detectors/test_todo_scanner.py` — 6 markdown HTML comment tests
- `tests/detectors/test_docs_drift.py` — 4 Poetry format tests
- `tests/fixtures/sample-repo/README.md` — added HTML comment TODOs
- `tests/fixtures/sample-repo/ground-truth.toml` — 2 new expected TPs
- `tests/fixtures/SAMPLE-REPO-GROUND-TRUTH.md` — documented markdown TODO TPs
- `docs/reference/tech-debt.md` — TD-005 and TD-008 resolved
- `docs/architecture/overview.md` — full rewrite to match implementation
- `docs/architecture/detector-interface.md` — Finding schema updated
- `roadmap/README.md` — phase labels and incremental status fixed
- `docs/reference/glossary.md` — 6 new terms added
- `README.md` — updated test count, clustering feature

## Previous Sessions

## Session 7 Summary

### Current Objective
Polish the project for real-world usability: README accuracy, config validation, incremental scanning.

### What Was Accomplished

**README updated to reflect reality:**
1. Status section updated: "Phase 2 complete" → "All MVP success criteria met"
2. Detectors listed: 5 (was 4), including git-hotspots
3. Default model corrected: `qwen3.5:4b` (was `qwen3:4b`)
4. New commands documented: `eval`, `create-issues`, `--incremental`
5. Configuration section added (`sentinel.toml` format)

**Config type validation (TD-004 resolved):**
6. `_validate_config()` checks key validity and type correctness at load time
7. Unknown keys raise `ConfigError` with clear message listing valid keys
8. Wrong types raise `ConfigError` with expected vs actual type
9. 6 tests: defaults, valid config, wrong type model, wrong type skip_judge, unknown key, partial config

**Incremental scan support:**
10. DB migration v4: `commit_sha TEXT` column on `runs` table
11. `_git_head_sha()` and `_git_changed_files()` helpers in runner
12. `prepare_incremental()` function: queries last completed run's SHA, computes diff
13. CLI `--incremental` flag wired through to `run_scan()` with `scope=INCREMENTAL`
14. Early exit with message when HEAD is unchanged since last run
15. `create_run()` and `_row_to_run()` handle `commit_sha` field
16. `get_last_completed_run()` query added to `runs.py`
17. 9 tests: SHA retrieval, changed file detection, prepare_incremental scenarios, persistence

### Decisions Made This Session
1. Config validation uses dataclass field introspection for type checking — no external validation library needed
2. Incremental scan uses git commit SHA comparison (not timestamps) for reliability across rebases
3. When HEAD is unchanged since last run, `--incremental` exits early with a message instead of running an empty scan
4. `git_hotspots` is inherently repo-wide — it does not filter by changed files (correct by design)

### Test Results
```
252 passed in 15.25s
ruff check: All checks passed
```

### Repository State
- **Phases**: 0–3 and 5 complete, Phase 4 in progress (git-hotspots done)
- **Implementation**: 18 Python modules in `src/sentinel/`
- **Tests**: 17 test files, 252 tests
- **Detectors**: todo-scanner, lint-runner, dep-audit, docs-drift, git-hotspots
- **CLI**: scan (with --incremental), eval, suppress, approve, history, create-issues
- **DB schema**: v4 (migration framework, finding persistence, llm_log, commit_sha)
- **Open questions**: 4 open (OQ-002, OQ-004, OQ-005, OQ-006), 3 resolved
- **ADRs**: 8 accepted
- **Tech debt**: 4 active (TD-001, TD-002, TD-005, TD-008), 4 resolved
- **Lint**: Clean (ruff)

### What Remains / Next Priority
1. TD-001: Context gatherer upgrade to embedding-based (needs OQ-004 resolution)
2. TD-002: Async detector interface (low priority)
3. TD-005: TODO comments in markdown invisible (low priority)
4. TD-008: Poetry pyproject.toml format (low priority)
5. Phase 4 remaining detectors: SQL anti-patterns, Semgrep, complexity/dead-code
6. Multi-repo support (OQ-005)
7. Finding grouping by root cause (e.g., 15 stale links from same moved directory)
8. Custom detector plugin system

### Blocked Items
None.

### Files Created This Session
- `tests/test_config.py` — 6 config validation tests
- `tests/test_incremental.py` — 9 incremental scan tests

### Files Modified This Session
- `README.md` — updated status, detectors, commands, model, config section
- `src/sentinel/config.py` — added `ConfigError`, `_validate_config()`
- `src/sentinel/core/runner.py` — `_git_head_sha()`, `_git_changed_files()`, `prepare_incremental()`, commit SHA storage
- `src/sentinel/store/db.py` — migration v4 (commit_sha column), SCHEMA_VERSION bump
- `src/sentinel/store/runs.py` — `commit_sha` in create/retrieve, `get_last_completed_run()`
- `src/sentinel/models.py` — `commit_sha` field on `RunSummary`
- `src/sentinel/cli.py` — `--incremental` flag on scan command
- `docs/reference/tech-debt.md` — TD-004 resolved

## Previous Sessions

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
