# Current State — Sentinel

> Last updated: Session 23 — Phase 7: Provider Abstraction complete

## Session 23 Summary

### Current Objective
Implement Phase 7: Provider Abstraction (ADR-010) — make the pipeline provider-agnostic.

### What Was Accomplished

**Phase 7: Provider Abstraction — Complete:**

1. **ModelProvider protocol** (`src/sentinel/core/provider.py`):
   - `@runtime_checkable` Protocol with `generate()`, `embed()`, `check_health()`
   - `LLMResponse` frozen dataclass for type-safe responses
   - `create_provider(config)` factory dispatching on `config.provider`

2. **OllamaProvider** (`src/sentinel/core/providers/ollama.py`):
   - Wraps `/api/generate`, `/api/embed`, `/api/tags`
   - Extracts all existing Ollama HTTP logic into a single cohesive class
   - Zero behavior change for existing users

3. **OpenAICompatibleProvider** (`src/sentinel/core/providers/openai_compat.py`):
   - Wraps `/v1/chat/completions`, `/v1/embeddings`
   - API key from env var (never in config), startup warning for cloud providers
   - Supports OpenAI, Azure OpenAI, vLLM, LM Studio, Together, etc.

4. **Config** (`src/sentinel/config.py`): Added `provider`, `api_base`, `api_key_env` fields

5. **All consumers refactored** to use `provider.generate()` / `provider.embed()`:
   - `judge.py`: removed `model`/`ollama_url` args, added `provider: ModelProvider`
   - `semantic_drift.py`: uses `provider` from config dict
   - `docs_drift.py`: uses `provider` from config dict
   - `context.py`: uses `provider.embed()` instead of `embed_texts()`
   - `indexer.py`: uses `provider.embed()` instead of `embed_texts()`
   - `runner.py`: creates/receives provider, wires to all consumers
   - `cli.py`: `--provider`/`--api-base` options, `create_provider()` in scan/index
   - `web/app.py`: uses `create_provider()` for scan and eval endpoints

6. **Tests**: 711 passing (680 existing + 31 new provider tests)
   - New `tests/test_provider.py`: protocol compliance, factory, OllamaProvider, OpenAICompatibleProvider
   - New `tests/mock_provider.py`: `MockProvider` for test isolation
   - Updated: test_judge, test_integration, test_embeddings, test_indexer, test_docs_drift, test_semantic_drift, test_web

7. **OQ-010 resolved**: Protocol surface documented

8. **Docs updated**: Phase 7 marked complete, roadmap table updated, OQ-010 resolved

### Verification
- **Tests**: 711 passed, 3 skipped
- **Ruff**: All checks passed
- **Mypy strict**: Success (42 source files)
- **No production code** imports from `sentinel.core.ollama` anymore (kept for backward compat)

### Repository State
- **Tests**: 711 passing
- **VISION-LOCK**: v4.0 (unchanged)
- **ADR-010**: Implemented
- **Phase 7**: Complete
- **OQ-010**: Resolved

### Files Created
- `src/sentinel/core/provider.py`
- `src/sentinel/core/providers/__init__.py`
- `src/sentinel/core/providers/ollama.py`
- `src/sentinel/core/providers/openai_compat.py`
- `tests/test_provider.py`
- `tests/mock_provider.py`

### Files Modified
- `src/sentinel/config.py`
- `src/sentinel/core/judge.py`
- `src/sentinel/core/runner.py`
- `src/sentinel/core/context.py`
- `src/sentinel/core/indexer.py`
- `src/sentinel/cli.py`
- `src/sentinel/web/app.py`
- `src/sentinel/detectors/semantic_drift.py`
- `src/sentinel/detectors/docs_drift.py`
- `tests/test_judge.py`
- `tests/test_integration.py`
- `tests/test_embeddings.py`
- `tests/test_indexer.py`
- `tests/test_web.py`
- `tests/detectors/test_semantic_drift.py`
- `tests/detectors/test_docs_drift.py`
- `docs/reference/open-questions.md`
- `roadmap/phases/phase-7-provider-abstraction.md`
- `roadmap/README.md`

### What Remains / Next Priority
1. **Real-world validation**: Run semantic-drift on a real project and analyze accuracy
2. **Test-code coherence detector** (OQ-009): Compare tests vs implementations for semantic staleness
3. Phase 6b: Dead code / unused exports, unused dependencies, stale config / env drift
4. Phase 8: Capability-tiered detectors (now unblocked by Phase 7)
5. PyPI publication

---

## Session 20 Summary

### Current Objective
Critical analysis of detector value, vision recalibration, and docs alignment.

### What Was Accomplished

**VISION-LOCK v3.0 (strategic recalibration):**
- Archived v2.2 as `docs/vision/archive/VISION-LOCK-v2.md`
- Problem statement sharpened: cross-artifact inconsistency is the core unsolved problem
- Core concept reframed: LLM has two roles — judge (shipped) and analyst (next frontier)
- Risks updated with observed risks (LLM fabricates reasoning, detectors duplicate existing tools)
- Where We're Going rewritten: Phase 5 (semantic docs-drift, test-code coherence) with key insight — even a binary "needs review" signal is the high-value product
- Success criterion #10 added: "surface issues the dev didn't already know about" — partially met
- Honest Detector Value Assessment table added

**Strategy doc updated:**
- "What it should be good at" rewritten with cross-artifact analysis as the core differentiator
- Detector value tier table added
- Relationship to existing tools clarified — Sentinel is not a lint aggregator, it's a cross-artifact analyst

**Architecture overview updated:**
- Detector Tier 3 expanded to describe planned semantic detectors
- LLM Judge description expanded with planned analyst role
- Value assessment note added linking to VISION-LOCK tier table

**Open questions added:**
- OQ-008: How should semantic docs-drift pair doc sections with code?
- OQ-009: Can a 4B model reliably deliver test-code coherence signals?

**Tech debt added:**
- TD-011: Most detectors duplicate existing dev tooling (accepted, focus investment elsewhere)
- TD-012: git-hotspots provides statistics without insight

### Key Insight
Even if the LLM is too simple to describe HOW the docs are out of date or how to fix it, identifying THAT they need review is a big deal. The binary "in sync / needs review" triage signal is the core product value for cross-artifact detectors. A 4B model can deliver this reliably.

### Repository State
- **Tests**: 626 passing, 90% code coverage (unchanged — docs-only session)
- **Docs changed**: VISION-LOCK.md (v3.0), strategy.md, overview.md, open-questions.md, tech-debt.md, VISION-LOCK-v2.md (archive)

### What Remains / Next Priority
1. Phase 5: Build semantic docs-drift detector (OQ-008)
2. Phase 5: Build test-code coherence detector (OQ-009)
3. Phase 5b: Dead code / unused exports detector (tree-sitter)
4. Phase 5b: Unused dependencies detector
5. Phase 5b: Stale config / env drift detector
6. Real-world validation on Go/Rust repos
7. PyPI publication

### Decisions Made This Session
- VISION-LOCK v3.0 warranted (not a revision) due to strategic misalignment between vision promise and implementation reality
- Binary "needs review" signal is the product — detailed explanations are a bonus
- New development investment should prioritize cross-artifact semantic detectors over improving existing lint wrappers
- Existing low-value detectors (lint, todo, etc.) kept — cheap to maintain, useful for some repos

---

## Session 19 Summary

### Current Objective
Resolve TD-010 (configurable num_ctx), then run real-world validation on ~/wyoclear (a Next.js/TypeScript + Python project) and deeply analyze accuracy.

### What Was Accomplished

**Slice 1 — TD-010: Configurable num_ctx (commit e5fc834):**
1. Added `num_ctx: int = 2048` to `SentinelConfig` in config.py
2. Threaded through cli.py → runner.py → judge.py → Ollama API call
3. Added to `_INIT_TEMPLATE` as commented-out option
4. Updated TD-010 status to Resolved in tech-debt.md

**Slice 2 — COMMON_SKIP_DIRS refactor (commit f0bb090):**
- Root cause: first wyoclear scan produced 3,836 todo-scanner findings because `.next` build dir wasn't skipped
- Created `COMMON_SKIP_DIRS` frozenset in `detectors/base.py` (19 entries: `.next`, `.turbo`, `out`, `coverage`, etc.)
- Updated all 7 detectors to import from base; go-linter adds `vendor`, rust-clippy adds `target`
- Result: todo-scanner went from 3,836 → 1 finding

**Slice 3 — Docs-drift false positive filters (commit 6b0988f):**
- `_check_inline_path()` was matching non-path patterns (Next.js imports, dates, URLs, CSS)
- Added 4 filter stages: URL-without-scheme, date patterns, bare two-segment non-paths
- 5 new tests for FP prevention + regression
- Result: docs-drift went from 130 → 79 findings (51 fewer FPs)

**Slice 4 — Fix regex patterns misidentified as markdown links (commit 0a27bc2):**
- `[JS](\d+)` in markdown tables was parsed as a broken link. Added regex metacharacter filter in `_check_link_target`.
- 1 new test, 620 tests passing.

**Slice 5 — Fix dedup for same-target different-doc findings (commit 7fa82a6):**
- Two docs referencing the same missing file now get the same fingerprint (deduped). `_effective_file_path()` uses `referenced_path`/`target` instead of source doc path.
- 2 new tests, 622 tests passing.

**Slice 6 — Skip inline paths in markdown strikethrough (commit d2353e2):**
- Paths in `~~strikethrough~~` blocks are intentionally documenting deleted files — no longer flagged.
- 1 new test, 623 tests passing.

**Slice 7 — Reviewer-requested num_ctx tests (commit 211f624):**
- Added tests: `test_judge_custom_num_ctx` (4096 reaches Ollama API), `test_loads_custom_num_ctx`, `test_rejects_wrong_type_for_num_ctx`.
- 626 tests passing.

**Real-world validation — wyoclear scan results (3 scans):**

| Metric | Scan 1 (pre-fix) | Scan 2 (FP filters) | Scan 3 (all fixes) |
|---|---|---|---|
| Raw findings | 195 | 144 | 136 |
| After dedup | 159 | 112 | 104 |
| Confirmed | 137 | 95 | 92 |
| Likely FP | 22 | 17 | 12 |
| Judge time | 303.6s | 275.5s | 179.0s |
| Inconsistent verdicts | 4 | 4 | **0** |

Final scan 3 accuracy by detector:

| Detector | Raw | After Dedup | Confirmed | FP | Accuracy Notes |
|---|---|---|---|---|---|
| complexity | 19 | 19 | 18 | 1 | 100% (1 borderline correctly rejected) |
| docs-drift | 77 | 58 | 56 | 2 | 97% (2 FPs correctly identified by judge) |
| git-hotspots | 16 | 16 | 7 | 9 | 100% (9 config/doc files correctly rejected) |
| lint-runner | 29 | 10 | 10 | 0 | 100% (all legitimate ruff findings) |
| todo-scanner | 1 | 1 | 1 | 0 | 100% |

**Docs-drift deep accuracy (final):**
- Stale links: 37 confirmed — all verified as genuinely broken links (100% accurate)
- Stale path refs: 19 confirmed — all verified as genuinely missing files (100% accurate)
- Judge inconsistency: **0** (was 4 in scan 2) — dedup fix completely resolved this
- 2 remaining FPs correctly identified by judge: `session-phase-strip.tsx` (documented as deleted in table, not strikethrough), `2026/Introduced/HB0011.pdf` (example URL, not local path)

**LLM Judge quality assessment (qwen3.5:4b):**
- Good at: rejecting config/doc files in git-hotspots, rejecting borderline complexity cases, confirming lint findings, identifying deliberately-documented deletions
- Bad at: fabricating plausible reasons to confirm noise when given low-quality detector input (scan 1 confirmed 42/42 obvious non-paths)
- Lesson confirmed: detector precision must be high first; the judge is a refinement layer, not a noise filter
- Severity assignment is reasonable: complexity CC>20 = high, broken links = medium, ruff warnings = low

**Key finding: deterministic detector precision matters more than LLM judgment.** The FP filters added across slices 3-6 reduced findings from 159 → 104 (35% reduction) and FPs from 22 → 12 (45% reduction), with judge time dropping 41%. The judge now handles only genuinely ambiguous cases.

### Test Results
```
626 passed, 90% coverage
ruff check: All checks passed
mypy strict: All checks passed
```

### Repository State
- **Tests**: 626 passing, 90% code coverage
- **Commits this session**: 7 (e5fc834, f0bb090, 6b0988f, 0a27bc2, 7fa82a6, d2353e2, 211f624)
- **Detectors**: 9 with centralized COMMON_SKIP_DIRS
- **Real-world tested**: ~/wyoclear (Next.js + Python, ~102 source files), 3 successive scans

### What Remains / Next Priority
1. Real-world validation on Go/Rust repos
2. Consider making `starts_with_known_dir` list configurable instead of hardcoded
3. Improve dep-audit to detect Python subdirectory projects (e.g., ~/wyoclear/ingestion/)
4. PyPI publication (needs credentials)
5. TD-002: Async detector interface (low priority)

### Blocked Items
- PyPI publishing: needs PyPI credentials / trusted publisher setup

### Decisions Made This Session
- COMMON_SKIP_DIRS is the single source of truth for skip directories across all detectors
- Detector precision must be improved before relying on LLM judgment — the 4B model fabricates plausible reasoning to confirm noise
- Centralized skip dirs future-proofs against new framework build artifacts
- Docs-drift dedup uses target path (not source doc) for stale references — eliminates judge inconsistency
- Reviewer subagent run before final commit; all minor findings addressed

### Lessons Learned
- Real-world testing exposed 5 bugs (missing .next skip, FP path matching, regex-as-link, dedup inconsistency, strikethrough awareness) that unit tests would never catch
- The LLM judge is NOT a viable noise filter — it confirmed 42/42 obvious non-paths in scan 1 with fabricated reasoning
- Judge inconsistency on duplicate inputs is fully solved by better dedup (give it one chance, not two)
- Iterative fix-scan-analyze cycles are extremely productive: each re-scan quantifies the improvement precisely
- Total improvement across 3 scans: 159 → 104 findings (-35%), 22 → 12 FPs (-45%), 304s → 179s judge time (-41%)

---

## Session 18 Summary

### Current Objective
Address reviewer findings from Session 17, add CI coverage, update vision lock, model benchmarking.

### What Was Accomplished

**Slice 1 — Reviewer fixes (8 files):**
1. CONTRIBUTING.md: added 7 missing source modules
2. README.md: fixed test count 610→614, added --quiet to options table
3. sample-cli-session.txt: fixed Status: active → Status: new
4. go_linter.py: fixed evidence/context args formatting
5. eslint_runner.py: fixed _SKIP_DIRS to use relative_to(repo_root)
6. Architecture overview: added scan-all to trigger modes, setup/diagnostics section
7. Glossary: added entries for scan-all, doctor, init
8. test_cli.py: strengthened doctor JSON test

**Slice 2 — CI coverage reporting:**
9. Added pytest-cov>=5.0 to dev dependencies
10. CI now runs with --cov=sentinel --cov-report=term-missing --cov-report=xml
11. Coverage artifact uploaded on Python 3.12 runs
12. Current coverage: 90%

**Slice 3 — Vision lock v2.2:**
13. Marked 5/7 "Where We're Going" items as shipped
14. Expanded "What Exists Today" section for full reality
15. Phase 4 (Extended Detectors) marked complete

**Slice 4 — Model benchmarking:**
16. Benchmarked qwen3.5:4b vs qwen3.5:9b-q4_K_M on self-scan
17. 4B: 5m8s, 53 tok/s, fits GPU fully. 9B: 14m22s, 18.5 tok/s, partial CPU offload
18. 9B is 2.9× slower with more aggressive FP rejection
19. Prompts avg ~523 tokens — well within 2048 default num_ctx
20. Explicitly set num_ctx: 2048 in judge.py
21. Documented in docs/reference/model-benchmarks.md

### Test Results
```
614 passed, 90% coverage
ruff check: All checks passed
mypy strict: All checks passed
```

### Repository State
- **Implementation**: 37 Python modules in `src/sentinel/`
- **Tests**: 614 passing, 90% code coverage
- **Detectors**: 9 (todo-scanner, lint-runner, eslint-runner, go-linter, rust-clippy, dep-audit, docs-drift, git-hotspots, complexity)
- **CLI**: 14 commands (scan, scan-all, init, doctor, show, suppress, approve, create-issues, history, eval, eval-history, index, serve, --version)
- **Web UI**: 16+ routes, annotations, eval trend chart, run comparison, two-pass clustering, dark/light mode
- **DB schema**: v7
- **CI**: GitHub Actions (Python 3.11/3.12/3.13 matrix, ruff, mypy, pytest with coverage)
- **Packaging**: PyPI-ready wheel with templates/static included
- **Lint/Type**: Clean (ruff, mypy strict)
- **Model benchmarks**: 4B recommended (53 tok/s, full GPU), 9B too slow with CPU offload

### What Remains / Next Priority
1. Real-world validation on non-Python repos (Go, Rust, JS/TS projects)
2. TD-002: Async detector interface (low priority)
3. `pip install local-repo-sentinel` publish to PyPI (needs credentials)
4. Improve docs_drift coverage (currently 81%)
5. Investigate 9B model's high FP rejection rate
6. Benchmark with embeddings enabled

### Blocked Items
- PyPI publishing: needs PyPI credentials / trusted publisher setup
- Formal model quality eval: needs ground-truth fixture with LLM-sensitive findings

### Decisions Made This Session
- num_ctx: 2048 is adequate for current prompt sizes (avg 523 tokens)
- qwen3.5:4b confirmed as best default (fits 8GB VRAM, 3× faster than 9B)
- Phase 4 marked complete (all planned detectors shipped)

---

## Session 15 Summary

### Current Objective
CLI as AI-agent interface, multi-language detector support, web UI clustering, persistent eval metrics.

### What Was Accomplished

**Slice 1 — CLI JSON output (`--json-output` flag):**
1. Added `--json-output` flag to `scan`, `show`, `history`, `eval`, `create-issues` commands
2. `scan --json-output`: outputs `{run, findings[], report_path}` as structured JSON
3. `show --json-output`: outputs full finding dict including evidence and metadata
4. `history --json-output`: outputs array of run summaries
5. `eval --json-output`: outputs `{precision, recall, passed, total_findings, ...}`
6. `create-issues --json-output`: outputs `{results[]}` with per-finding success/error
7. Added `RunSummary.to_dict()` and `EvalResult.to_dict()` serialization methods
8. Updated CLI help text to document JSON output and exit codes
9. 7 new tests for JSON output across all commands

**Slice 2 — eslint-runner detector (multi-language foundation):**
10. New `eslint-runner` detector wrapping ESLint and Biome for JS/TS linting
11. Tries Biome first (faster, zero-config), falls back to ESLint
12. Auto-skips repos without JS/TS files (checks for `package.json` or `*.js/*.ts`)
13. Supports incremental and targeted scan scopes (filters to JS/TS extensions)
14. Maps ESLint severity levels and Biome diagnostic categories to Sentinel severities
15. Security-sensitive rules (`no-eval`, `suspicious/*`) elevated to HIGH
16. 19 new tests (properties, parsing, detection, fallback, timeout, scope filtering)

**Slice 3 — Web UI directory clustering:**
17. Run detail page now groups 3+ findings in the same directory into collapsible `<details>` elements
18. Reuses existing `cluster_findings()` from markdown report clustering
19. Folder icon + directory path label on cluster summaries
20. Checkboxes preserved inside clusters for bulk actions
21. New CSS for .finding-cluster, .cluster-summary, .cluster-body

**Slice 4 — Persistent eval metrics:**
22. DB migration v6: `eval_results` table for storing evaluation metrics over time
23. `sentinel eval` now persists results to the repo's configured DB (not `:memory:`)
24. New `sentinel eval-history` CLI command to view past eval results
25. `eval_store.py`: `save_eval_result()`, `get_eval_history()`, `StoredEvalResult.to_dict()`
26. New `/eval/history` web page with eval trend table
27. Eval page POST now saves results to DB
28. Link from eval page to eval history

### Decisions Made This Session
1. `--json-output` flag name (not `--format json`) — explicit, boolean, no ambiguity
2. Biome preferred over ESLint — faster, zero-config, auto-fallback to ESLint
3. eslint-runner uses detector name "eslint-runner" regardless of which tool runs — consistent fingerprints
4. Biome byte offsets not converted to line numbers — imprecise mapping, null is better than wrong
5. Web clustering reuses `cluster_findings()` from report module — single implementation
6. Eval results persisted to repo's configured DB (not :memory:) — enables tracking over time
7. `eval-history` as separate CLI command (not merged into `eval`) — cleaner separation

### Test Results
```
488 passed in 34.23s
ruff check: All checks passed
mypy strict: All checks passed (34 source files)
eval: 100% precision, 100% recall (15 TPs, 0 FPs)
```

### Files Changed
- `src/sentinel/cli.py` — `--json-output` flag on 5 commands, `eval-history` command
- `src/sentinel/models.py` — `RunSummary.to_dict()` method
- `src/sentinel/core/eval.py` — `EvalResult.to_dict()` method
- `src/sentinel/core/runner.py` — eslint-runner import
- `src/sentinel/detectors/eslint_runner.py` — new detector (ESLint/Biome wrapper)
- `src/sentinel/store/db.py` — migration v6 (eval_results table)
- `src/sentinel/store/eval_store.py` — new module (eval result persistence)
- `src/sentinel/web/app.py` — clustering, eval persistence, eval-history route
- `src/sentinel/web/templates/run_detail.html` — cluster rendering
- `src/sentinel/web/templates/eval_history.html` — new template
- `src/sentinel/web/templates/eval.html` — history link
- `src/sentinel/web/templates/base.html` — nav link fix
- `src/sentinel/web/static/style.css` — cluster styles
- `tests/test_cli.py` — 7 new JSON output tests
- `tests/detectors/test_eslint_runner.py` — 19 new detector tests
- `tests/test_web.py` — 3 new tests (clustering, eval history)
- `tests/test_store.py` — 4 new eval store tests
- `tests/test_embeddings.py` — schema version test fix
- `README.md` — updated detector count, JSON output docs
- `docs/architecture/overview.md` — updated detector list/tiers
- `docs/vision/VISION-LOCK.md` — v2.1 with new features

### Repository State
- **Implementation**: 27+ Python modules in `src/sentinel/`
- **Tests**: 25+ test files, 488 tests (61 web tests, 27 CLI tests, 19 eslint-runner tests)
- **Web UI**: Dark/light mode, 12 routes, bulk triage, settings, eval + eval history, clustering
- **CLI**: 11 commands, `--json-output` on 6 key commands
- **Web pages**: /, /runs, /runs/{id}, /findings/{id}, /scan, /github, /settings, /eval, /eval/history + actions
- **Detectors**: 7 (todo-scanner, lint-runner, eslint-runner, dep-audit, docs-drift, git-hotspots, complexity)
- **DB schema**: v6
- **Open questions**: 2 open (OQ-005, OQ-006), 5 resolved
- **ADRs**: 9 accepted
- **Tech debt**: 2 active (TD-002 async, TD-009 scheduling), 7 resolved
- **Lint**: Clean (ruff)
- **Type check**: Clean (mypy strict, 34 files)
- **Vision**: v2.1

### What Remains / Next Priority
1. Go linter integration (golangci-lint)
2. JSON output for `suppress`/`approve` commands
3. Eval metrics chart visualization (sparklines or SVG in web UI)
4. TD-002: Async detector interface (low priority)
5. Multi-repo support (OQ-005)
6. Packaging & distribution (PyPI)

### Blocked Items
None.

### Vision Completion Status
All 9 success criteria met. Multi-language support started with JS/TS. Eval metrics dashboard shipped.

---

## Session 13 Summary

### Current Objective
Web UI feature expansion: bulk triage actions, settings dashboard, evaluation page.

### What Was Accomplished

**Slice 1 — Bulk approve/suppress:**
1. `POST /runs/{run_id}/bulk-action` — accepts `action` (approve/suppress), `finding_ids` list, optional `reason`
2. Checkboxes on every finding row, per-severity-group "select all" toggle
3. Sticky bulk action bar: shows count, Approve Selected, Suppress Selected buttons
4. htmx toast + page reload on completion
5. 10 new tests (TestBulkActions class)

**Slice 2 — Settings page (`/settings`):**
6. Displays all SentinelConfig fields with current values and types
7. Shows sentinel.toml detection status (found vs using defaults)
8. GitHub env var status (SENTINEL_GITHUB_OWNER/REPO/TOKEN: set/not set)
9. 5 new tests (TestSettingsPage class)

**Slice 2 — Eval page (`/eval`):**
10. Form: repo path + optional ground-truth file path
11. Runs detectors with skip_judge=True, compares to ground truth TOML
12. Displays precision/recall as color-coded stat cards with pass/fail thresholds
13. Lists missing expected findings and unexpected false positives
14. 5 new tests (TestEvalPage class), including mocked eval success

**Navigation:**
15. Added Eval and Settings links to header nav bar

### Decisions Made This Session
1. Bulk action processes each finding individually — simpler, leverages existing store functions, correct suppression-by-fingerprint behavior
2. Page reloads after bulk action — simpler than complex htmx partial updates
3. Settings page is read-only — editing config belongs in sentinel.toml, not the web UI
4. Eval page runs with skip_judge=True in an in-memory DB — same behavior as `sentinel eval` CLI

### Test Results
```
456 passed in 28.14s
ruff check: All checks passed
mypy strict: All checks passed
```

### Files Changed
- `src/sentinel/web/app.py` — 3 new route handlers (bulk_action, settings_page, eval_page) + route registration
- `src/sentinel/web/templates/run_detail.html` — checkboxes, bulk form, bulk action bar
- `src/sentinel/web/templates/settings.html` — new template
- `src/sentinel/web/templates/eval.html` — new template
- `src/sentinel/web/templates/base.html` — 2 new nav links (Eval, Settings)
- `src/sentinel/web/static/app.js` — bulk selection/submit JS
- `src/sentinel/web/static/style.css` — bulk bar, checkbox, settings table, threshold styles
- `tests/test_web.py` — 20 new tests

### Repository State
- **Implementation**: 25+ Python modules in `src/sentinel/`
- **Tests**: 24+ test files, 456 tests (58 web tests, up from 38)
- **Web UI**: Dark/light mode, 11 routes, bulk triage, settings, eval
- **CLI**: 10 commands (scan, eval, suppress, approve, show, history, create-issues, index, serve)
- **Web pages**: /, /runs, /runs/{id}, /findings/{id}, /scan, /github, /settings, /eval + actions
- **Detectors**: 6 (todo-scanner, lint-runner, dep-audit, docs-drift, git-hotspots, complexity)
- **DB schema**: v5
- **Open questions**: 2 open (OQ-005, OQ-006), 5 resolved
- **ADRs**: 9 accepted
- **Tech debt**: 1 active (TD-002 async), 1 active (TD-009 scheduling), 7 resolved
- **Lint**: Clean (ruff)
- **Type check**: Clean (mypy strict)

### What Remains / Next Priority
1. TD-002: Async detector interface (low priority)
2. Phase 4 remaining detectors: SQL anti-patterns, Semgrep, test-runner (deferred)
3. Multi-repo support (OQ-005)
4. VISION-REVISION-005 to document Settings + Eval pages as shipped

### Blocked Items
None.

### Vision Completion Status
All 7 MVP success criteria met. Web UI significantly exceeds VR-004 scope.

---

## Session 12 Summary

### Current Objective
Web UI overhaul: dark mode design system, CLI feature parity (GitHub issue creation, configurable scan, suppress with reason), repo selection.

### What Was Accomplished

**Complete CSS redesign ("Night Watch" theme):**
1. Dark-first design system with warm amber accent on deep navy-black backgrounds
2. Light mode with warm stone tones, toggled via button with localStorage persistence
3. Typography: Bricolage Grotesque (distinctive variable font) + JetBrains Mono (code)
4. CSS custom properties for full theming: severity colors, status colors, surfaces, borders
5. Responsive layout with 1200px max-width, mobile-friendly breakpoints
6. No-flash theme loading via inline script before render

**New pages:**
7. `/scan` (GET) — Configurable scan form: custom repo path, model override, embedding model, skip-judge, incremental checkboxes
8. `/github` — GitHub Issues dashboard: config status indicator, list of approved findings with severity badges, Create Issues + Dry Run buttons
9. `/github/create-issues` (POST) — Issue creation endpoint with htmx result rendering; handles both configured and unconfigured GitHub states

**Enhanced existing pages:**
10. Run detail: severity stat cards (critical/high/medium/low counts), back link to runs list, improved filter bar
11. Finding detail: suppress with inline reason text input, status-aware actions (shows different messages for approved/suppressed/resolved), recurrence info display
12. Runs list: card wrapper for table, scope badges styled as amber, page headers with subtitles
13. Empty states: sentinel shield SVG, link to /scan page

**Infrastructure:**
14. `app.js` — Theme toggle function + toast auto-dismiss observer (MutationObserver)
15. Toast notification system via htmx (CSS animations for slide-in/out)
16. Active nav link highlighting based on current URL path
17. Repo indicator in header showing current repo basename
18. Path validation for user-supplied scan targets (not for app-configured paths)

### Decisions Made This Session
1. Dark mode as default — matches the "Night Watch" sentinel theme and reduces eye strain for morning report review
2. Bricolage Grotesque font — distinctive, optical sizing, avoids common AI-slop fonts (Inter, Roboto, Arial)
3. GitHub token from env vars only (not web form) — security: don't accept sensitive credentials via HTTP forms
4. Scan form validates user-supplied paths but trusts already-configured app state paths
5. htmx fragments for GitHub issue results (no full page reload)

### Test Results
```
436 passed in 26.46s
ruff check: All checks passed
mypy strict: All checks passed
```

### Repository State
- **Implementation**: 25+ Python modules in `src/sentinel/`
- **Tests**: 24+ test files, 436 tests (38 web tests, up from 28)
- **Web UI**: Dark/light mode, 9 routes, GitHub issue workflow, configurable scan
- **CLI**: 10 commands (scan, eval, suppress, approve, show, history, create-issues, index, serve)
- **Web pages**: / (dashboard), /runs, /runs/{id}, /findings/{id}, /scan, /github + actions
- **Detectors**: 6 (todo-scanner, lint-runner, dep-audit, docs-drift, git-hotspots, complexity)
- **DB schema**: v5
- **Open questions**: 2 open (OQ-005, OQ-006), 5 resolved
- **ADRs**: 9 accepted
- **Tech debt**: 1 active (TD-002 async), 7 resolved
- **Lint**: Clean (ruff)
- **Type check**: Clean (mypy strict)

### What Remains / Next Priority
1. Bulk approve/suppress from run detail page (checkboxes + batch action)
2. User avatar/profile placeholder for future personalization
3. Settings page (view config, potentially edit)
4. TD-002: Async detector interface (low priority)
5. Phase 4 remaining detectors: SQL anti-patterns, Semgrep, test-runner (deferred)
6. Eval page in web UI (run evaluation from browser)

### Blocked Items
None.

---

## Session 11 Summary

### Current Objective
Post-MVP feature implementation: web UI (VISION-REVISION-002), complexity detector, `sentinel show` command, report naming fix.

### What Was Accomplished

**Report naming fix:**
1. CLI default changed: when `-o` not provided, `output_path=None` so runner generates `report-{run.id}.md`

**Complexity detector (new):**
2. AST-based detector for cyclomatic complexity (>10) and function length (>50 lines)
3. Severity scaling: >2x threshold = HIGH, >1.5x = MEDIUM, else LOW
4. Handles syntax errors gracefully, skips non-Python files
5. 20 tests covering CC calculation, function lines, integration, edge cases

**`sentinel show` command (new):**
6. Inspect any finding by ID: title, detector, category, severity, confidence, status, fingerprint, location, description, evidence, recurrence
7. 2 new tests

**Web UI — `sentinel serve` (VISION-REVISION-002):**
8. Starlette + Jinja2 + htmx server-rendered interface, no JS build step
9. Routes: / (redirect to latest run), /runs (history), /runs/{id} (detail), /findings/{id} (detail), /findings/{id}/action (approve/suppress), /scan (trigger)
10. Filter findings by severity, status, or detector via query params
11. Scan Now button triggers POST /scan from the browser
12. htmx inline approve/suppress actions (progressive enhancement)
13. Minimal CSS with severity/status badges
14. Added `Finding.id` field to model for DB round-tripping
15. Added `check_same_thread` param to `get_connection` for web use
16. Dependencies: starlette>=0.40, jinja2>=3.1, uvicorn>=0.30, python-multipart>=0.0.9 (optional `[web]` group)
17. 23 web tests, all passing

### Decisions Made This Session
1. Complexity detector thresholds: CC>10, function lines>50 (industry standard)
2. Web UI uses optional dependency group `[web]` — core CLI works without web deps
3. `Finding.id` added as optional field (None by default, populated from DB)
4. `check_same_thread=False` needed for Starlette's threadpool execution
5. No built-in scheduler — existing decision stands (cron/systemd)
6. htmx from CDN (unpkg) for progressive enhancement

### Test Results
```
421 passed in 26.49s
ruff check: All checks passed
mypy: All checks passed
```

### Repository State
- **Implementation**: 25+ Python modules in `src/sentinel/`
- **Tests**: 24+ test files, 421 tests
- **Detectors**: todo-scanner, lint-runner, dep-audit, docs-drift, git-hotspots, complexity + custom detector plugin system
- **CLI**: scan, eval, suppress, approve, show, history, create-issues, index, serve (10 commands)
- **Web UI**: Starlette-based, server-rendered with htmx, filter/approve/suppress/scan
- **DB schema**: v5 (with Finding.id round-tripping)
- **Open questions**: 2 open (OQ-005, OQ-006), 5 resolved
- **ADRs**: 9 accepted
- **Tech debt**: 1 active (TD-002 async), 7 resolved
- **Lint**: Clean (ruff)
- **Type check**: Clean (mypy strict)
- **Docs**: Updated README with show/serve commands

### What Remains / Next Priority
1. TD-002: Async detector interface (low priority)
2. Phase 4 remaining detectors: SQL anti-patterns, Semgrep, test-runner (deferred)
3. Multi-repo support (OQ-005)
4. Finding grouping by root cause (deeper than directory clustering)
5. VISION-LOCK.md may need a revision to reflect web UI as shipped capability

### Blocked Items
None.

### Vision Completion Status
All 7 MVP success criteria met. VISION-REVISION-002 web UI features delivered.

---

## Session 10 Summary

### Current Objective
Docs-code alignment, mypy type safety, expose targeted scan, false positive reduction, test coverage for untested modules, custom detector plugin system.

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

**False positive reduction:**
23. Docs-drift: suffix matching for inline paths — `store/db.py` resolved correctly when `src/sentinel/store/db.py` exists (12 FPs eliminated)
24. TODO scanner: `(?!-)` negative lookahead rejects compound words like `todo-scanner` (precision 88% → 100%)

**Self-scan validation:**
25. Ran `sentinel scan` against own codebase — 33 findings, 0 FPs on own docs
26. Eval: 100% precision, 100% recall on ground truth (15 TPs)

**Test coverage expansion (58 new tests):**
27. `tests/test_cli.py`: 19 CLI integration tests via CliRunner — all 8 commands + custom detectors E2E
28. `tests/test_indexer.py`: 23 indexer unit tests — skip logic, file collection, chunk_file, build_index
29. `tests/test_ollama.py`: 11 Ollama utility tests — check_ollama, embed_texts, failure paths
30. `tests/test_detectors_base.py`: 5 new tests for custom detector plugin loading
31. Reviewer findings addressed: incremental scan precondition assert, os.devnull portability, dead code removal, empty embeddings edge case, non-UTF8 file test

**Custom detector plugin system:**
32. `detectors_dir` config option — path to directory with custom detector .py files
33. `load_custom_detectors()` in base.py — dynamic import via importlib, auto-registration
34. Runner integration — loads custom detectors at scan time when configured
35. CLI passes detectors_dir through config to scan
36. Documentation: README example (LicenseDetector), detector-interface.md updated

### Decisions Made This Session
1. No built-in scheduler — cron/systemd timer documented in README
2. `test-runner` detector deferred to Phase 2+
3. Targeted scan paths not validated as click.Path — detectors handle gracefully
4. dep-audit and git-hotspots are inherently repo-scoped, don't filter by target_paths
5. mypy strict mode with ignore_missing_imports — zero errors is the baseline going forward
6. `(?!-)` negative lookahead is sufficient for compound word rejection in TODO scanner
7. Docs-drift suffix matching resolves module-relative paths against all repo files
8. Custom detector plugin uses importlib.util (standard library, no extra deps)

### Test Results
```
376 passed in 25.74s
ruff check: All checks passed
mypy: Success: no issues found in 29 source files
eval: 100% precision, 100% recall (15 TPs, 0 FPs)
```

### Repository State
- **Phases**: 0–3 and 5 complete, Phase 4 in progress (git-hotspots done)
- **Implementation**: 21 Python modules in `src/sentinel/`
- **Tests**: 22 test files, 376 tests
- **Detectors**: todo-scanner (with markdown HTML comments), lint-runner, dep-audit, docs-drift (with Poetry), git-hotspots + custom detector plugin system
- **CLI**: scan (with --incremental, --embed-model, --target), eval, suppress, approve, history, create-issues, index
- **DB schema**: v5 (migration framework, finding persistence, llm_log, commit_sha, chunks + embed_meta)
- **Open questions**: 2 open (OQ-005, OQ-006), 5 resolved
- **ADRs**: 9 accepted
- **Tech debt**: 1 active (TD-002 async), 7 resolved
- **Lint**: Clean (ruff)
- **Type check**: Clean (mypy strict)
- **Ground truth**: 15 expected TPs in eval fixture
- **Self-scan**: Validated — 33 findings, 0 FPs on own docs
- **Eval**: 100% precision, 100% recall
- **Docs**: All aligned with actual implementation
- **Custom detectors**: Plugin system via `detectors_dir` config

### What Remains / Next Priority
1. TD-002: Async detector interface (low priority)
2. Phase 4 remaining detectors: SQL anti-patterns, Semgrep, complexity/dead-code, test-runner (deferred)
3. Multi-repo support (OQ-005)
4. Finding grouping by root cause (deeper than directory clustering)
5. Web UI for report review (future)

### Blocked Items
None.

### Vision Completion Status
All 7 MVP success criteria are met:
1. ✅ Developer can install, scan, and get a useful morning report
2. ✅ Report scannable in <2 minutes (one line per finding, expandable evidence, severity tags)
3. ✅ FP rate subjectively acceptable (100% precision on ground truth)
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
