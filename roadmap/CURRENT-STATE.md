# Current State — Sentinel

> Last updated: Session 51 — ADR-018 benchmark rigor, expanded sample-repo, richer compatibility metrics

**Phase Status**: Blocked: Phase 15 ICD precision is Poor on all non-frontier models. Benchmark infrastructure now strengthened (ADR-018). Awaiting human decision: (a) close phase with honest Poor ratings and ICD disabled by default, (b) proceed to vision expansion, or (c) execute benchmarking plan first.

## Latest Session Summary

### Current Objective
Codify benchmark rigor as a design decision. Expand sample-repo for meaningful LLM detector benchmarks. Show richer metrics (precision, raw counts, sample size) on the detectors page.

### What Was Accomplished

#### ADR-018: Benchmark Rigor as Core Engineering Discipline
- Codified that FP rate alone is insufficient — precision, recall, raw counts, and sample size all matter
- Minimum sample requirements: N<5 = raw counts only, N≥10 across ≥2 repos = "Established"
- Ground truth files are first-class engineering artifacts
- Strengthens ADR-016 (benchmark-driven model quality)

#### Expanded Sample-Repo (3 → 10 source files, 37 → 85 ground truth TPs)
- New modules: `utils.py`, `models.py`, `handlers.py`, `services.py`
- New tests: `test_utils.py`, `test_handlers.py`, `test_services.py`
- New docs: `docs/guides/api-reference.md`, `docs/architecture.md`
- Each file contains a mix of seeded drift issues and correct code (true negatives)
- LLM detector ground truth: semantic-drift=10, test-coherence=15, inline-comment-drift=18, intent-comparison=9

#### Richer Compatibility Matrix
- `CompatibilityEntry` now has `tp_count`, `finding_count`, `repos_tested` fields
- Detectors page shows raw counts (`3/7 TP`) when available, falls back to FP rate
- ICD entries now show precise counts with repos tested

#### Ground Truth Gap Documentation
- Both real-repo ground truth files (sentinel, pip-tools) now document the LLM detector annotation gap
- TD-061 filed: LLM detectors have no real-repo ground truth (High severity)
- Benchmarking plan written at docs/analysis/benchmarking-plan.md

### Key Commits This Session
- `b036604` feat(benchmarks): ADR-018 benchmark rigor, expanded sample-repo, richer metrics

### Repository State
- **Tests**: 1401 passing, 37 skipped (tree-sitter)
- **Coverage**: ~85% (unchanged — no source code changes)
- **Ruff + mypy strict**: clean
- **VISION-LOCK**: v6.2 (Phase 15)

### What Remains / Next Priority
1. **Execute benchmarking plan Phase 1**: Run sample-repo benchmarks across all 5 model classes — this can be done immediately with the expanded ground truth
2. **Execute benchmarking plan Phase 2**: Run LLM detectors on real repos (sentinel, pip-tools), annotate findings, build ground truth
3. **Phase 15 decision**: Close with honest ratings or proceed to vision expansion
4. **TD-059**: Benchmark docs-drift LLM path
5. **TD-061**: Fill real-repo LLM detector ground truth

### Decisions Made
- ADR-018 accepted: benchmark rigor is non-negotiable engineering discipline
- FP rate alone is insufficient for quality ratings — precision, recall, raw counts, sample size all matter
- Ground truth is a first-class artifact — the benchmark fixture needs to be big enough for statistical significance
- Current LLM detector ratings on real repos are informal and need reproducible benchmarks

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
