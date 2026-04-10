# Current State — Sentinel

> Last updated: Session 27 (continued) — GitHub e2e test, real-world validation, ground truth

## Latest Session Summary

### Current Objective
End-to-end GitHub issue creation test, real-world validation on pip-tools, first ground truth corpus, OQ resolution, sample regeneration, FP pattern documentation.

### What Was Accomplished

#### GitHub Issue Creation — End-to-End Validated
- Scanned sentinel repo (195 findings), approved 2, ran dry-run (passed), created 2 real issues on `jcentner/sentinel-test-repo`
- Verified dedup: re-approving + creating skips existing issues by fingerprint match
- Full flow: scan → approve → dry-run → create → dedup all work correctly

#### Real-World Validation: pip-tools
- Scanned `jazzband/pip-tools` (commit eed26c9): 50 findings from 7 active detectors
- 19 findings individually annotated, 25 assumed-TP (complexity + todo)
- **Overall precision: 76%** (38 TP / 50 total)
- **Non-trivial detector precision: 15%** (3 TP / 20 non-complexity-non-todo) — concerning
- 5 actionable FP patterns identified (see TD-040, TD-041, TD-042)

#### FP Patterns Discovered (filed as tech debt)
- **TD-040**: Dead-code misses intra-file usage + dynamic entry points (6/6 FP)
- **TD-041**: Docs-drift treats example text as file paths (3/3 FP)
- **TD-042**: Unused-deps misses plugin/entry-point loading (3/3 FP)

#### OQ Resolutions
- **OQ-014** resolved: First real-world ground truth at `benchmarks/ground-truth/pip-tools.toml`
- **OQ-017** resolved: PAT-only for GitHub (OAuth deferred — not worth the complexity)
- **OQ-018** resolved: Hybrid docs approach (in-repo for dev docs, wiki for user guides)

#### Samples Regenerated
- `samples/` updated with current output from `tests/fixtures/sample-repo` (was stale from Session 8)
- CLI session, report, and JSON all regenerated from real current output

#### Bug Fix
- Runner log: "produced 1 findings" → "produced 1 finding" (pluralization)

#### CI Fix
- `sentinel eval --json-output` is a boolean flag; CI was passing filename as positional arg

### Verification
- **Tests**: 1013 passed, 3 skipped
- **Ruff**: Clean
- **Mypy**: Clean (51 files)
- **Eval gates**: Both pass (basic + full-pipeline)
- **Reviewer**: Run, findings addressed

### Repository State
- **Tests**: 1013 passing
- **VISION-LOCK**: v4.6 (unchanged)
- **Tech debt items**: 42 total, 32 resolved, 10 remaining (7 low + 3 medium)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 14

### What Remains / Next Priority

#### Highest leverage: fix FP patterns (TD-040, TD-041, TD-042)
The pip-tools validation showed 100% FP rate on dead-code, docs-drift, and unused-deps detectors. Fixing these 3 issues would dramatically improve real-world precision:
1. **TD-040**: Dead-code intra-file usage check (easy fix, high impact: 6 FPs eliminated)
2. **TD-041**: Docs-drift example text heuristic (medium fix: 3 FPs eliminated)
3. **TD-042**: Unused-deps plugin/entry-point awareness (medium fix: 3 FPs eliminated)

#### Other priorities
1. Validate fixes by re-scanning pip-tools after detector improvements
2. Annotate more repos from `docs/reference/test-repos.md`
3. PyPI publication
4. Phase 10 planning (advanced detectors)

---

## Previous Sessions (Archived)

Session summaries for Sessions 1-26 are preserved in git history. Key milestones:

- **Sessions 1-3**: Vision lock, Phase 1 plan, core pipeline
- **Sessions 7-8**: Web UI, SQLite store, CLI commands, sample repo fixture
- **Sessions 10-13**: Provider abstraction, embedding-based context, incremental scanning
- **Sessions 15-19**: Advanced detectors, eval system, clustering, synthesis
- **Sessions 20-22**: Per-detector providers, benchmarking, sample repo expansion
- **Sessions 23-24**: Systemic review — resolved 25/26 tech debt items
- **Session 25**: Full-pipeline eval with replay provider
- **Session 26**: Systemic review audit, gap fixes

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
