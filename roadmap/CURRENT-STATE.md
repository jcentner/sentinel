# Current State — Sentinel

> Last updated: Session 42 — Web UI UX audit and fixes

**Phase Status**: Blocked: Vision Expansion — awaiting human approval

## Latest Session Summary

### Current Objective
Web UI UX walkthrough: audit all pages as a user, identify friction/bugs, fix them.

### What Was Accomplished

#### UX audit and 14 fixes (Session 42)
Full interactive walkthrough of every web UI page discovered 14 issues across 4 priority levels. All fixed, tested (1290 tests + 178 web/model/store), and browser-verified.

**P0 — Critical (CSRF)**:
- 7 of 10 POST forms were missing `csrf_token` hidden inputs → all forms now work
- CSRF error response styled with navigation instead of bare text

**P1 — High**:
- Stat cards showed filtered counts as totals → now show unfiltered totals regardless of active filter
- Finding detail back link used `javascript:history.back()` → now uses `/runs/{run_id}`
- Added `run_id` field to `Finding` dataclass, populated from DB in `_row_to_finding()`

**P2 — Medium**:
- Nav link renamed "Issues" → "GitHub" to match page content
- Home redirect changed from `/runs/{latest_id}` to `/runs` (listing page)
- Detectors page: added anchor-based TOC for 7 sections
- Filter selects auto-submit on change via `onchange`

**P3 — Low**:
- Repo badge tooltip: "Active repository: {path}"
- Timestamps: Jinja2 `|ts` filter for consistent `%Y-%m-%d %H:%M` formatting
- Cluster label "." replaced with "(repo root)"
- Light theme: improved contrast (warm off-white, visible borders)
- Scan page: htmx loading indicator
- CSS: `.htmx-indicator` and `.htmx-request` rules

#### Files modified (15)
- `src/sentinel/models.py` — `Finding.run_id` field
- `src/sentinel/store/findings.py` — `_row_to_finding()` populates `run_id`
- `src/sentinel/web/app.py` — home redirect to `/runs`
- `src/sentinel/web/csrf.py` — styled error page
- `src/sentinel/web/routes/runs.py` — unfiltered `total_counts`
- `src/sentinel/web/shared.py` — `_format_ts()` Jinja2 filter
- `src/sentinel/web/static/style.css` — light theme, htmx indicators
- `src/sentinel/web/templates/base.html` — nav rename, tooltip
- `src/sentinel/web/templates/compatibility.html` — TOC + anchor IDs
- `src/sentinel/web/templates/eval.html` — CSRF token
- `src/sentinel/web/templates/finding_detail.html` — CSRF tokens, back link
- `src/sentinel/web/templates/llm_log.html` — auto-submit, timestamp filter
- `src/sentinel/web/templates/run_detail.html` — CSRF, stat cards, cluster label, auto-submit
- `src/sentinel/web/templates/scan.html` — CSRF, htmx loading
- `tests/test_web.py` — updated redirect assertion

### Repository State
- **Tests**: 1290 passing, 3 skipped
- **VISION-LOCK**: v5.6
- **Tech debt items**: 10 active
- **Open questions**: 2 partially resolved (OQ-009, OQ-019), 2 open (OQ-006, OQ-016)
- **ADRs**: 16
- **Detectors**: 18
- **Commits this session**: 1

### What Remains / Next Priority
1. **Vision Expansion** — all vision goals complete, proposal below

## Vision Expansion Proposal

### What was accomplished

All three "Where We're Going" goals from VISION-LOCK v5.6 are complete:

1. **Web UI as first-class interaction surface** — Settings, detectors, doctor, LLM call log, embed index pages. All planned pages shipped. (Sessions 35–39)
2. **Phase 10: Advanced detectors** — 4 detectors shipped: cicd-drift, inline-comment-drift, architecture-drift, intent-comparison. 18 total detectors. (Sessions 40–41)
3. **Cross-detector intelligence** — Two-phase execution with risk signals. LLM detectors prioritize high-churn files. (Session 39)

The system also has: pluggable providers (3 shipped), entry-points plugin system, benchmark-driven prompt adaptation (ADR-016), 88% confirmation rate, 1290 tests, VISION-LOCK v5.6.

### What was learned

- **Binary prompts are robust** — semantic-drift works well even at 4B. Simple "needs_review / in_sync" signals are reliable across models.
- **test-coherence needs stronger models** — 40% FP at 4B, 15% at cloud-nano. The quality cliff is real.
- **Multi-artifact prompts need frontier models** — intent-comparison is ADVANCED tier; pairwise analysis is the practical ceiling for basic/standard models.
- **Python AST is the substrate** — All 4 LLM detectors extract structure via `ast`. JS/TS/Go/Rust repos get zero LLM analysis. This is the biggest remaining coverage gap.
- **Ground truth is thin** — 1 repo (pip-tools) with 50 findings. TD-045 notes this is too small for statistical confidence.
- **Serial LLM is the speed bottleneck** — TD-016: 50 findings = 3.3 min, 100 = 7 min for judging. The only medium-severity tech debt.

### Proposed next directions (priority order)

#### 1. Multi-language LLM detectors
**Gap**: All 4 LLM detectors are Python-only. JS/TS, Go, and Rust repos get deterministic findings but zero cross-artifact analysis. Sentinel already has `eslint-runner`, `go-linter`, `rust-clippy` — the deterministic layer exists.
**What**: Extend semantic-drift, test-coherence, inline-comment-drift to JS/TS (most impactful: largest user base after Python). Go and Rust as follow-ons. Requires language-specific AST extraction (tree-sitter or language parsers).
**Evidence**: docs/reference/test-repos.md lists JS/TS repos (vite, next.js). The semantic-drift detector already has a generic (non-AST) code extraction fallback but it's low quality.

#### 2. Parallel LLM execution
**Gap**: TD-016 — serial LLM calls for judging are the only medium-severity bottleneck. Scans with 100+ findings take 7+ minutes for the judge pass alone.
**What**: Async/parallel LLM calls for judge, synthesis, and LLM-assisted detectors. Requires `asyncio`-based provider protocol or thread pool. Needs careful DB connection handling (sqlite is single-writer).
**Evidence**: TD-002 notes sync detector interface. TD-016 has measured timings.

#### 3. Benchmark infrastructure expansion
**Gap**: Only 3 models benchmarked. 2 new detectors have zero data. Ground truth is 1 repo. Cloud-small and cloud-frontier are completely untested.
**What**: (a) Make `sentinel benchmark` write results to `llm_log` for web drill-down (OQ-019). (b) Add ground truth for 2-3 more repos from the test-repos list. (c) Benchmark intent-comparison and inline-comment-drift on multiple models. (d) Add `sentinel llm-log` CLI command for parity.
**Evidence**: compatibility-matrix.md shows extensive ❓ Untested entries. TD-045. OQ-019 partially resolved.

#### 4. CLI/Web parity completion
**Gap**: Web has rich triage features (annotations, comparisons, bulk actions) CLI lacks. CLI has operational commands (benchmark, prune, scan-all, index) web lacks.
**What**: Add web UI for triggering benchmark runs, viewing benchmark details, embedding index builds. Add CLI commands for `sentinel llm-log`, `sentinel compare`, bulk approve/suppress. Not all need both — prioritize by user workflow.
**Evidence**: Research shows 5 CLI features not in web, 4 web features not in CLI.

#### 5. Quality-of-life and polish
**What**: Resolve remaining low-severity tech debt (TD-024 json-output envelope, TD-039 hardcoded counts, TD-041 docs-drift FP from example text). Resolve OQ-016 (message list protocol). Small improvements that compound user trust.

---

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
