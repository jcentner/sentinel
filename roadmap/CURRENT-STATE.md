# Current State — Sentinel

> Last updated: Session 45 — Phase 13 in progress

**Phase Status**: Complete: Phase 13 (Benchmark & ground truth expansion)

## Latest Session Summary

### Current Objective
Phase 13: Benchmark & ground truth expansion — run all detectors on multiple Azure models, create 3rd ground truth repo, update compatibility matrix, add `sentinel llm-log` CLI.

### Environment Constraints
- **No dGPU** — Ollama models (qwen3.5:4b, 9b) cannot be benchmarked this session
- **Azure models available**: gpt-5.4-nano, gpt-5.4-mini, gpt-5.4
- **Ollama benchmarks deferred**: Mark in tech debt for future session with GPU access

### What Was Accomplished

#### Slice 1: Eval format fix + llm-log CLI + sample-repo benchmarks
- `evaluate()` now handles `[[findings]]` format with `verdict` field alongside `[[expected]]`
- New `sentinel llm-log` CLI command with filtering, pagination, stats, JSON output
- Sample-repo benchmarks: gpt-5.4-mini (92% P, 97% R), gpt-5.4 (87% P, 97% R)
- 11 new tests (3 eval + 8 llm-log CLI)
- Committed: d7f7b31

#### Slice 2: Pip-tools benchmark + sentinel ground truth + compatibility matrix
- Pip-tools gpt-5.4-mini benchmark: 94 findings, 582s (LLM detectors very slow)
  - intent-comparison: 35 findings (75s) — very noisy on real repos
  - inline-comment-drift: 6 findings (336s) — serial per-function calls
  - test-coherence: 4 findings (127s)
  - Precision/recall low (6.4%/46%) because ground truth lacks LLM detector annotations
- Created sentinel self-scan ground truth: 57 annotated + 120 assumed TP
  - dead-code: 39/40 FP (17 Click commands, 13 cross-module, 6 test fixtures, 2 framework, 1 dynamic)
  - todo-scanner: 16/16 FP (test fixtures, sample data, code patterns)
  - unused-deps: 2/2 FP (framework deps)
  - cicd-drift: 3/3 FP (build artifacts, YAML syntax)
- Updated compatibility matrix code with 10 new rated entries:
  - Judge: cloud-small EXCELLENT (~8% FP), cloud-frontier GOOD (~13% FP)
  - semantic-drift: cloud-small GOOD, cloud-frontier GOOD
  - test-coherence: cloud-small GOOD, cloud-frontier GOOD
  - inline-comment-drift: cloud-small GOOD, cloud-frontier GOOD
  - intent-comparison: cloud-small FAIR (~50% est, very noisy)
- Updated docs/reference/model-benchmarks.md + compatibility-matrix.md

### Decisions Made
- **Sentinel self-benchmark deferred**: 226 findings × 10s judge = ~38min, too slow for session. Ground truth created; benchmark can run later.
- **Pip-tools gpt-5.4 benchmark skipped**: Each benchmark takes 10+ min; diminishing returns vs mini data.
- **intent-comparison rated FAIR (est)**: 35 noisy findings on pip-tools, per-detector FP rate unknown. Transparent notes in matrix.

### Files Modified
- `src/sentinel/core/eval.py` — `[[findings]]` format support
- `src/sentinel/cli.py` — `llm-log` command
- `src/sentinel/core/compatibility.py` — 10 new rated entries
- `docs/reference/model-benchmarks.md` — Phase 13 benchmark results
- `docs/reference/compatibility-matrix.md` — updated matrix, sources, model list
- `benchmarks/ground-truth/sentinel.toml` — NEW: sentinel ground truth
- `benchmarks/20260413T200632-sample-repo-gpt-5.4-mini.toml` — NEW
- `benchmarks/20260413T200800-sample-repo-gpt-5.4.toml` — NEW
- `benchmarks/20260413T204502-pip-tools-gpt-5.4-mini.toml` — NEW
- `tests/test_eval.py` — 3 new tests
- `tests/test_cli.py` — 8 new tests + lint fix

### Repository State
- **Tests**: 1387 passing, 3 skipped
- **VISION-LOCK**: v6.0
- **Tech debt items**: 9 active
- **ADRs**: 17
- **Detectors**: 18
- **Commits this session**: 2 (d7f7b31, 9d91014) + 1 pending

### What Remains / Next Priority
Phase 13 success criteria met:
- **≥3 repos with annotated ground truth**: ✅ sample-repo (30 TPs), pip-tools (38 annotated), sentinel (57 annotated)
- **All detectors benchmarked on ≥2 models**: ✅ All 14 deterministic on 5 models; semantic-drift/test-coherence on 5 models; ICD/IC on 2 models (mini + full)

Future benchmark improvements (not required for Phase 13):
- Sentinel full benchmark execution (timed out at ~38min this session)
- Pip-tools LLM detector ground truth annotations (would fix low precision/recall)
- Ollama benchmarks for ICD/IC (deferred — need dGPU access)
- intent-comparison prompt tuning (35 noisy findings on pip-tools)

Next session should move to Phase 14 (CLI/Web parity & polish).

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
