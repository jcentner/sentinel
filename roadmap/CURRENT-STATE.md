# Current State — Sentinel

> Last updated: Session 52 — Phase 0+1 benchmarking: purge + sample-repo baselines

**Phase Status**: In Progress — executing benchmarking plan. Phase 1 (sample-repo baselines) complete. Phase 2 (real-repo annotation) next.

## Latest Session Summary

### Current Objective
Execute the benchmarking plan (docs/analysis/benchmarking-plan.md) to build statistically meaningful benchmark data for all detectors.

### What Was Accomplished

#### Phase 0: Purge Old Benchmark Data
- Removed 38 stale benchmark TOML files from `benchmarks/` (pre-expanded sample-repo, prior detector versions)
- Reset all LLM detector COMPATIBILITY_MATRIX entries to UNTESTED
- Ground truth files and README preserved

#### Phase 1: Sample-Repo Baselines (4 models × 4 LLM detectors)
Ran all LLM detectors on expanded sample-repo (10 files, 85 ground truth TPs) with 4 model classes:

| Detector | 4B (P/R) | 9B (P/R) | Nano (P/R) | Mini |
|---|---|---|---|---|
| semantic-drift | 50%/10% (1/2) | 50%/10% (1/2) | 50%/10% (1/2) | 0 findings |
| test-coherence | 60%/20% (3/5) | 67%/13% (2/3) | 60%/20% (3/5) | 0 findings |
| inline-comment-drift | 64%/50% (9/14) | 60%/83% (15/25) | 52%/89% (16/31) | 0 findings |
| intent-comparison | 44%/44% (4/9) | 18%/22% (2/11) | 27%/44% (4/15) | 0 findings |

Key insights:
- **gpt-5.4-mini produced ZERO LLM findings** — model too conservative for seeded fixture issues
- **semantic-drift recall uniformly 10%** — detector only checks top-level README sections, misses api-reference.md and architecture.md
- **test-coherence recall 13-20%** — misses subtle parameter/return drift
- **inline-comment-drift is the most productive LLM detector** — highest recall across all models
- **intent-comparison: 4B surprisingly outperforms 9B and nano on precision** (44% vs 18% vs 27%)

COMPATIBILITY_MATRIX updated with empirical tp/n/repos data per ADR-018.
5. **TD-061**: Fill real-repo LLM detector ground truth

### Decisions Made
### Key Commits This Session
- `5675e85` chore(benchmarks): purge 38 stale benchmark results, reset matrix to UNTESTED
- `20e2969` feat(benchmarks): Phase 1 sample-repo baselines — 4 models, empirical matrix

### Repository State
- **Tests**: 1401 passing, 37 skipped (tree-sitter)
- **Ruff + mypy strict**: clean
- **VISION-LOCK**: v6.2 (Phase 15)
- **Benchmark files**: 4 fresh sample-repo baselines (4B, 9B, nano, mini)

### What Remains / Next Priority
1. **Benchmarking plan Phase 2**: Run LLM detectors on real repos (sentinel, pip-tools), annotate findings, build ground truth — critical for "Established" ratings (N≥10, ≥2 repos)
2. **Investigate mini's zero findings**: gpt-5.4-mini found 0 LLM issues on sample-repo — try on real repos to determine if too conservative everywhere or just on fixtures
3. **Investigate semantic-drift 10% recall**: detector only checks README sections per heading — misses api-reference.md and architecture.md ground truth. Design gap or intentional scope limitation?
4. **Benchmarking plan Phase 3**: Update compatibility matrix with combined sample-repo + real-repo data
5. **TD-059**: Benchmark docs-drift LLM path
6. **TD-061**: Fill real-repo LLM detector ground truth (addressed by Phase 2)

### Decisions Made
- ADR-018 accepted: benchmark rigor is non-negotiable engineering discipline
- Old benchmark data purged to avoid confusion with stale results
- gpt-5.4 frontier excluded from benchmarks per user instruction (cost control)
- OpenAI API key available at `.oai` for nano/mini benchmarks only

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
