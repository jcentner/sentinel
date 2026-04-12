# Current State — Sentinel

> Last updated: Session 41 — Phase 10 complete: intent-comparison detector

**Phase Status**: Blocked: Vision Expansion — awaiting human approval

## Latest Session Summary

### Current Objective
Phase 10: Complete advanced detectors — ship intent-comparison (multi-artifact triangulation).

### What Was Accomplished

#### Intent comparison detector (Session 41)
- New `intent-comparison` LLM-assisted detector (cross-artifact category)
- First ADVANCED-tier detector — requires frontier-class models
- Multi-artifact triangulation: gathers code, docstring, tests, doc sections per function
- Only triggers when 3+ artifacts available (pairwise detectors cover 2-artifact cases)
- AST symbol extraction, test lookup (exact + prefix match), doc lookup (backtick refs)
- Binary LLM prompt with basic/enhanced mode (ADR-016)
- Risk-based file sorting via churn signals (TD-043)
- Per-file (10) and per-scan (50) LLM call limits
- 55 tests, reviewer findings fixed (_build_evidence elif→independent if, artifact name leniency)

#### Phase 10 now complete
All 4 Phase 10 detectors shipped:
- cicd-drift (deterministic, Session 40)
- inline-comment-drift (LLM-assisted, Session 40)
- architecture-drift (deterministic, Session 40)
- intent-comparison (LLM-assisted, Session 41)

#### Docs updated
- VISION-LOCK v5.6: 18 detectors, Phase 10 marked complete
- detector-interface.md: new row for intent-comparison, cross-artifact category added
- overview.md: Tier 3 description updated, detector list updated
- compatibility-matrix.md: intent-comparison row (untested, ADVANCED tier)
- README.md: 18 detectors, test count 1290

### Repository State
- **Tests**: 1290 passing, 3 skipped
- **VISION-LOCK**: v5.6
- **Tech debt items**: 10 active
- **Open questions**: 2 partially resolved (OQ-009, OQ-019), 2 open (OQ-006, OQ-016)
- **ADRs**: 16
- **Detectors**: 18 (was 17)
- **Commits this session**: 2

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
