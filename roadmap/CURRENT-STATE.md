# Current State — Sentinel

> Last updated: Session 50 — CI coverage fixed, benchmark integrity documented, LLM detector evaluation

**Phase Status**: In Progress — Phase 15 ICD work paused; addressing quality/integrity gaps and unblocking CI.

## Latest Session Summary

### Current Objective
Fix CI coverage failure, document benchmark integrity requirements, comprehensively evaluate all LLM detector prompts/context quality, address docs-drift benchmark gap.

### What Was Accomplished

#### CI Coverage Fixed (81% → 85%)
- **Root cause**: CI installed `[dev,web,detectors]` but not `[multilang]`. Tree-sitter tests (32) were skipped in CI, causing extractors.py coverage to drop from 87% to 45%.
- **Fix**: Added `multilang` to CI install. Added 13 new tests (7 for `findings` CLI, 3 for `prune` CLI, 3 for `prune_old_data` store).
- **Result**: 1435 tests pass, coverage 85.23% (threshold: 85%).

#### Benchmark Integrity Requirements Documented
- Added non-negotiable rules to `benchmarks/README.md`: empirical only, no estimates, statistical significance (N≥5 for rates), synthesized data is not evidence, separate deterministic/LLM metrics, document provenance.
- Fixed TD-057 description that said "Local 4B/9B=Good (<25% est)" — corrected to UNTESTED.
- Fixed model-benchmarks.md that said "FP rate (estimated)" — corrected to "(measured)".
- Tracked as TD-060 for ongoing enforcement.

#### Comprehensive LLM Detector Evaluation
Created `docs/analysis/llm-detector-evaluation.md` with full analysis of all 5 LLM-assisted detectors:

| Detector | Assessment | Key Finding |
|----------|-----------|-------------|
| semantic-drift | ✅ Well-designed | Works across all model tiers, no prompt changes needed |
| test-coherence | ✅ Good design | 4B fails because task requires understanding test framework patterns |
| inline-comment-drift | ✅ Solid | Nano struggles with "incomplete ≠ wrong" distinction; slow (serial calls) |
| intent-comparison | ❌ Over-scoped | 4-way triangulation exceeds model capacity; dominant FP is hallucinated evidence |
| docs-drift (LLM) | ❓ Unbenchmarked | No prompt adaptation, no capability_tier, no benchmark data |

Key cross-cutting findings:
- Context truncation (1500 chars) is a hidden FP driver — models flag "missing behavior" that exists past the truncation
- Binary prompts are validated as right default for 3 of 4 detectors (ADR-016 approach confirmed)
- ICD's fundamental problem is task scope, not prompting — two-pass verification is most promising direction
- The "basic = binary signal" approach could go further: consider auto-disabling POOR-rated detector×model combos

#### docs-drift Benchmark Gap Addressed
- Added docs-drift to LLM-assisted matrix (all ❓ Untested)
- Updated hybrid note explaining when LLM path activates and what users should know
- Created TD-059 to track: add capability_tier, prompt adaptation, benchmarks

### Key Commits This Session (Session 50)
- `7a20fb6` fix(ci): add multilang deps + tests for findings/prune to pass 85% coverage
- `12d484b` docs(benchmarks): add integrity requirements, LLM detector evaluation, fix estimated ratings

### Repository State
- **Tests**: 1435 passing (13 new)
- **Coverage**: 85.23% (CI threshold: 85%)
- **CLI commands**: 21
- **Web routes**: 21
- **VISION-LOCK**: v6.2 (Phase 15)

### What Remains / Next Priority
1. **Phase 15 decision**: ICD confirmed as fundamentally over-scoped at current capability levels. Options: (a) close phase with honest Poor ratings and ICD disabled by default, (b) implement two-pass verification to target hallucination FP.
2. **TD-059**: Benchmark docs-drift LLM path, add prompt adaptation and capability_tier.
3. **TD-060**: Enforce benchmark integrity on future rating claims.
4. **4b/9b re-benchmark**: Local model benchmarks stale — need dGPU system.
5. **Performance**: inline-comment-drift serial execution (~303s on pip-tools) needs async batching.

### Decisions Made
- Benchmark integrity requirements are non-negotiable (documented in benchmarks/README.md)
- Estimated ratings are not acceptable — mark as ❓ Untested or provide empirical data
- ICD's dominant FP pattern (hallucinated evidence) is a model capacity issue, not a prompt issue
- Binary prompts are the correct default for all LLM detectors (ADR-016 validated)

## Vision Expansion Proposal

All goals in VISION-LOCK v6 "Where We're Going" are implemented. Here's what the project has accomplished and where it could go next.

### What Was Accomplished (v5-v6)
- **Async pipeline** (Phase 11): 4.5x speedup via concurrent judge/synthesis, parallel detector execution
- **Multi-language** (Phase 12): Tree-sitter integration for JS/TS, all 4 LLM detectors cross-language
- **Benchmark system** (Phase 13): 3 ground truth repos, per-model×detector quality ratings, per-category eval
- **CLI/Web parity** (Phase 14): 21 CLI commands, 21 web routes, bulk ops, benchmark page, JSON standardization

### What Was Learned
1. **Cross-artifact analysis is the differentiator** — lint/todo detectors overlap with existing tools; docs-drift, test-coherence, and semantic-drift find issues nothing else does
2. **Intent-comparison's >90% FP rate** shows that multi-artifact triangulation needs carefully calibrated prompts and post-LLM filtering, not just more artifacts
3. **Benchmark data drives trust** — switching from assumed tiers to empirical ratings changed how we think about model-detector quality
4. **Small model quality is a ceiling** — 4B models cap at FAIR for LLM detectors; cloud-nano is the quality step-change
5. **Web UI as first-class surface** unlocked triage workflows that CLI alone can't support

### Proposed Next Directions

**Direction 1: Intent-comparison v2 — post-LLM filtering + calibration** ✅ IMPLEMENTED (Phase 15)

**Direction 2: Incremental scanning performance**
Currently scans the full repo even in incremental mode (detectors receive changed_files but still walk the tree). For large repos (10K+ files), startup cost is dominated by file discovery and embedding index building. Implement lazy file discovery, cached AST parsing, and smarter context gathering that only reads changed neighborhoods.

**Direction 3: Scheduled scan + notification**
While Sentinel itself doesn't schedule, the morning report workflow is the core UX. Add a lightweight `sentinel watch` daemon that triggers periodic scans and saves reports. Integrate with OS notifications (desktop, email, Slack webhook) for "new findings since last scan" alerts.

**Direction 4: Finding clustering and trend analysis**
Findings accumulate across runs but there's no cross-run analysis. Add finding clustering (group related findings), trend detection (worsening code areas), and a web dashboard showing health trajectory per directory/module over time.

**Direction 5: Go/Rust LLM detectors**
Tree-sitter already supports Go and Rust, but only JS/TS extractors were built. Extend the extractors module to support Go and Rust function/docstring extraction, enabling all 4 LLM detectors for those languages.

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
