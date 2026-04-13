# Current State — Sentinel

> Last updated: Session 45 (continued) — Data integrity audit

**Phase Status**: Complete: Phase 13 (Benchmark & ground truth expansion)

## Latest Session Summary

### Current Objective
Data integrity audit of compatibility matrix and benchmark documentation. User reviewed the web UI and challenged the accuracy of published ratings.

### Environment Constraints
- **No dGPU, no Ollama** — Azure OpenAI only (gpt-5.4-nano, gpt-5.4-mini, gpt-5.4)
- Local model benchmarks deferred indefinitely

### What Was Accomplished

#### Audit: Benchmark data provenance
- Discovered `sentinel benchmark` does NOT run judge or synthesis — only raw detector `.detect()` output
- Judge ratings for cloud-small (EXCELLENT) and cloud-frontier (GOOD) were **fabricated** — derived from overall benchmark precision which is raw detector output, not judge quality
- Headline precision dominated by ~27 deterministic findings identical across models — not meaningful for model comparison
- gpt-5.4 benchmark based on ~12 Azure API calls on a 3-file fixture

#### Slice 1: Honest compatibility ratings (9c63901)
- Judge cloud-small/frontier: EXCELLENT/GOOD → UNTESTED (benchmark skips judge)
- ICD: added cloud-nano GOOD ~15% (est), fixed local model notes, added (est) suffix to all ICD rates (no automated ground truth)
- IC cloud-small: FAIR ~50% → POOR >90% (est), documented design issues
- Added full nano benchmark: sample-repo 40 findings, 85% precision, 100% recall
- Fixed model-benchmarks.md: "full scan with judge" → "raw detector output only"
- Fixed ground truth count: 61 → 57 (matches TOML)
- Added "How These Numbers Were Measured" caveat about benchmark vs judge
- TD-057: intent-comparison needs redesign (>90% FP, no post-LLM filtering)
- TD-058: benchmark conflates deterministic and LLM precision
- Moved resolved TD-045 to tech-debt-resolved.md

### Intent-Comparison Root Cause (TD-057)
- Runs with `model_capability=basic` despite declaring `advanced` (warning-only gate)
- No post-LLM filtering — every hallucinated contradiction becomes a finding
- Prompt lacks concrete FP examples
- 50-call budget with no quality check
- 0 findings on sample-repo (too few 3-artifact symbols), 35 on pip-tools (all likely FP)

### Decisions Made
- **All ICD FP rates marked (est)**: Human review of ≤5 findings, no automated ground truth
- **IC rated POOR not FAIR**: 35/35 likely FP on pip-tools is not "fair"
- **Judge ratings UNTESTED**: Benchmark doesn't run judge; honest > optimistic

### Files Modified
- `src/sentinel/core/compatibility.py` — rewrote all LLM detector + judge entries
- `docs/reference/compatibility-matrix.md` — updated table, key findings, methodology
- `docs/reference/model-benchmarks.md` — fixed Phase 13 section, added nano data
- `docs/reference/tech-debt.md` — TD-057, TD-058, removed resolved TD-045
- `docs/reference/tech-debt-resolved.md` — added TD-045
- `benchmarks/20260413T213608-sample-repo-gpt-5.4-nano.toml` — NEW

### Repository State
- **Tests**: 858 passing (targeted), 3 skipped (ruff + mypy clean)
- **Commits this session (continued)**: 9c63901
- **Tech debt items**: 10 active (added TD-057, TD-058)

### What Remains / Next Priority
- intent-comparison redesign (TD-057) — highest impact quality fix
- Benchmark per-category precision (TD-058) — needed for meaningful model comparison
- Judge quality measurement from `sentinel scan` for cloud models
- Phase 14 (CLI/Web parity & polish)

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
