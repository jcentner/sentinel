# Current State — Sentinel

> Last updated: Session 45 (continued) — Benchmark system improvement

**Phase Status**: Complete: Phase 13 (Benchmark & ground truth expansion)

## Latest Session Summary

### Current Objective
Improve benchmark system to produce meaningful, defensible data. User reviewed web UI, challenged data quality, demanded better benchmarks.

### Environment Constraints
- This system: Azure OpenAI only (gpt-5.4-nano, gpt-5.4-mini, gpt-5.4), no dGPU
- Other system has dGPU for local Ollama models

### What Was Accomplished

#### Slice 1: Honest compatibility ratings (9c63901)
- Judge cloud-small/frontier: EXCELLENT/GOOD → UNTESTED (benchmark skips judge)
- IC cloud-small: FAIR → POOR >90% est, documented design issues
- Fixed ground truth count, removed fabricated data
- TD-057: intent-comparison needs redesign, TD-058: benchmark precision conflation

#### Slice 2: Per-category benchmark precision + re-benchmarks (4e09f72)
- **Benchmark code**: Added `[benchmark.eval.deterministic]` and `[benchmark.eval.llm_assisted]` sections to TOML output with separate precision/recall. `compare_benchmarks()` shows category split. Per-detector precision in comparison table.
- **ICD ground truth**: Added 3 seeded TPs + 2 FP patterns to sample-repo ground truth (37 total TPs)
- **Re-benchmarked** all models on sample-repo + pip-tools with updated ground truth:
  - sample-repo nano: 92%P overall, **84.6% LLM precision** (ICD 60%P, TC 100%P, SD 100%P)
  - sample-repo mini: 97%P overall, **100% LLM precision** (ICD 100%P, TC 100%P, SD 100%P)
  - pip-tools nano: 49 LLM findings (16 ICD, 20 IC, 6 TC, 5 SD) — **no LLM ground truth**
  - pip-tools mini: 48 LLM findings (8 ICD, 31 IC, 3 TC, 4 SD) — **no LLM ground truth**
- **ICD ratings from real data**: nano FAIR ~40% (3/5 TP), mini EXCELLENT <10% (2/2 TP)
- **IC rated POOR** on both nano and mini (20-31 findings on pip-tools, all likely FP)
- **docs-drift tier fixed**: DETECTOR_INFO now matches code (`llm-assisted`, not `deterministic`)
- TD-058 resolved, VISION-LOCK updated, 7 new tests for category split code
- 909 tests passing, ruff + mypy clean

### Decisions Made
- **docs-drift classified as llm-assisted**: Code already declares it; DETECTOR_INFO was wrong
- **ICD nano rated FAIR**: 60% precision with ground truth, not estimated
- **IC nano rated POOR**: 20 findings on pip-tools, all likely FP (same design issues as mini)

### Repository State
- **Tests**: 909 passing (targeted), 3 skipped
- **Commits**: 9c63901, f49c61b, 4e09f72
- **Tech debt**: TD-057 (IC redesign) active, TD-058 resolved

### What Remains / Next Priority
- **Pip-tools LLM ground truth**: Manual review of ~48 LLM findings → real per-detector ratings on a meaningful codebase. Highest impact data improvement.
- **IC redesign (TD-057)**: Add hard capability gate, post-LLM filtering, FP examples in prompt
- **Judge quality measurement**: Run `sentinel scan` with cloud models and measure judge verdict distributions
- **Phase 14**: CLI/Web parity & polish

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
