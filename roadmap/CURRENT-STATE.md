# Current State — Sentinel

> Last updated: Session 46 — Phase 14 CLI/Web parity complete

**Phase Status**: Blocked: Vision Expansion — awaiting human approval

## Latest Session Summary

### Current Objective
Phase 14: Achieve feature parity between CLI and web UI. Resolve key tech debt items.

### What Was Accomplished

#### Setup: Catalog activations (0b75579)
- Activated 5 catalog items: tool-guardrails, context-checkpoint, designer agent, ci-verification skill, anti-slop skill
- Fixed tree-sitter skip guards in 4 detector test files
- Registered PreToolUse and PostToolUse hooks in autonomous-builder agent

#### Slice 1: CLI `sentinel compare` (6cc6a30)
- New command for run-to-run diff: new/resolved/persistent findings
- Supports `--json-output`. 3 new tests.

#### Slice 2: TD-024 JSON error standardization (51a116a)
- All error paths emit `{"error": "..."}` when `--json-output` is active
- TD-024 partially resolved (full envelope deferred as breaking change)

#### Slice 3: CLI bulk operations (2aca544)
- `sentinel bulk-approve --run <id>` or `--ids <1,2,3>`
- `sentinel bulk-suppress --run <id>` or `--ids <1,2,3> --reason <text>`
- 7 new tests.

#### Slice 4: Web benchmark page (560457b)
- `/benchmark` route: form, stat cards, per-detector results, save-to-disk
- 4 new web tests.

#### Slice 5: TD-057 intent-comparison disabled by default (eadc1d9)
- `enabled_by_default` property on Detector base class
- IntentComparisonDetector set to False. 3 new tests.

### Decisions Made
- **No full JSON envelope** — breaking change, standardized error shape sufficient
- **enabled_by_default property** — keeps decision close to detector code
- **OQ-016 deferred** — no current caller needs multi-turn messages
- **TD-041 deferred** — remaining docs-drift FP edge cases are low-priority

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
