# Current State — Sentinel

> Last updated: Session 47 — Phase 15 ICD v2

**Phase Status**: In Progress

## Latest Session Summary

### Current Objective
Phase 15: Intent-comparison v2 — post-LLM filtering + calibration. Goal: <25% FP rate.

### What Was Accomplished

#### Benchmark expansion (02646a7)
- qwen3.5:4b on sample-repo: 94% precision, 91% recall, 14.8s (all 18 detectors)
- qwen3.5:9b on sample-repo: 94% precision, 97% recall, 36.1s
- qwen3.5:4b self-scan: 398 findings incl. 5 ICD, 150s
- Local models achieve 80-83% LLM precision vs cloud 85-100%
- Updated model-benchmarks.md with full comparison tables

### Repository State
- **Tests**: 1378 passing, 36 skipped
- **CLI commands**: 21 (added compare, bulk-approve, bulk-suppress)
- **Web routes**: 21 (added /benchmark)
- **VISION-LOCK**: v6.1

### What Remains / Next Priority
- **Vision expansion**: All v6 goals (Phases 11-14) complete. Vision expansion proposal below.
- **Remaining parity gaps**: web prune, web multi-repo, CLI annotations, CLI GitHub status
- **TD-041**: 2 docs-drift FP edge cases
- **Intent-comparison redesign**: Needed for re-enablement

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

**Direction 1: Intent-comparison v2 — post-LLM filtering + calibration**
The highest-FP detector is also the highest-potential one. Redesign with structured confidence-weighting, concrete FP examples in prompts, and automatic filtering of vague/low-evidence contradictions. Gate on benchmark score, not tier label. Goal: <25% FP rate on cloud-nano.

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
