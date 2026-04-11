# Current State — Sentinel

> Last updated: Session 31 — LLM detector validation, dead-code FP fix, benchmark improvements

## Latest Session Summary

### Current Objective
Fix TD-044 (JS/TS dead-code FPs), validate LLM-assisted detectors across models, improve benchmarking system.

### What Was Accomplished

#### TD-044 Resolved: Dead-code JS/TS monorepo FP reduction
- Added barrel re-export tracking (`export * from`, `export { } from`)
- Added TypeScript type export/import patterns
- Added intra-file reference tracking for JS/TS (count-based, matching Python's existing approach)
- Added `import * as` namespace import handling (all exports consumed)
- Added package.json entry-point detection (main/exports/module/types fields)
- 7 new tests covering all new patterns. 55 dead-code tests total, all passing.

#### Benchmarking system improvements
- Decoupled `--skip-judge` from `--skip-llm` in benchmark CLI (previously aliased)
- Added `--api-key-env` flag to benchmark CLI for cloud provider testing
- Fixed OpenAI provider: `max_completion_tokens` for gpt-5.x models (auto-fallback to `max_tokens`)
- Added test fixtures for LLM detectors: `tests/fixtures/sample-repo/tests/` with seeded test-code drift

#### LLM detector validation — three models compared
Tested semantic-drift and test-coherence across qwen3.5:4b, qwen3.5:9b, and gpt-5.4-nano:

**Sample repo** (seeded fixture):
| Model | semantic-drift | test-coherence | Total | Time |
|-------|---------------|---------------|-------|------|
| qwen3.5:4b | 1 | 2 | 3 | 9.2s |
| qwen3.5:9b | 1 | 1 | 2 | 18.2s |
| gpt-5.4-nano | 1 | 1 | 2 | 4.7s |

**Sentinel self-scan** (real codebase):
| Model | semantic-drift | test-coherence | Total | Time |
|-------|---------------|---------------|-------|------|
| qwen3.5:4b | 15 | 14 | 29 | 84s |
| gpt-5.4-nano | 15 | 6 | 21 | 49s |

Key finding: gpt-5.4-nano is the most precise (estimated ~15% FP on test-coherence vs ~40% for 4B). Semantic-drift works well across all models. Full results in docs/reference/model-benchmarks.md.

#### Verification
- 1042 tests passing (+7 new dead-code tests, ruff + mypy strict clean)
- Sample repo eval: P=89%, R=100% (with LLM detectors contributing 3 additional findings)
- All 3 LLM detector benchmark runs saved to benchmarks/

### Repository State
- **Tests**: 1042 passing
- **VISION-LOCK**: v4.7
- **PyPI**: `repo-sentinel` v0.1.0 published
- **Tech debt items**: 42 total, 35 resolved, 7 remaining (6 low + 1 medium)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 14

### What Remains / Next Priority

#### Next priorities
1. **Full-pipeline scan** — Validate judge + synthesis + report end-to-end with a live model
2. **Test-coherence prompt refinement** — Reduce FP rate for mock-based and CLI integration tests
3. **Cross-detector data flow** (TD-043) — Let git-hotspots inform LLM detector targeting
4. **Ground truth expansion** (TD-045) — Add LLM detector entries to ground-truth.toml

---

## Previous Sessions (Archived)

Session summaries for Sessions 1-27 are preserved in git history. Key milestones:

- **Sessions 1-3**: Vision lock, Phase 1 plan, core pipeline
- **Sessions 7-8**: Web UI, SQLite store, CLI commands, sample repo fixture
- **Sessions 10-13**: Provider abstraction, embedding-based context, incremental scanning
- **Sessions 15-19**: Advanced detectors, eval system, clustering, synthesis
- **Sessions 20-22**: Per-detector providers, benchmarking, sample repo expansion
- **Sessions 23-24**: Systemic review — resolved 25/26 tech debt items
- **Session 25**: Full-pipeline eval with replay provider
- **Session 26**: Systemic review audit, gap fixes
- **Session 27**: GitHub e2e test, pip-tools validation, ground truth, sample regeneration

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
