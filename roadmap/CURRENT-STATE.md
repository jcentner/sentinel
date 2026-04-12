# Current State — Sentinel

> Last updated: Session 40 — Phase 10 detectors: cicd-drift + inline-comment-drift

**Phase Status**: In Progress

## Latest Session Summary

### Current Objective
Phase 10: Advanced detectors — ship new detectors for CI/CD config drift and inline comment drift.

### What Was Accomplished

#### CI/CD config drift detector (Session 40)
- New `cicd-drift` deterministic detector (config-drift category)
- GitHub Actions: local action refs, working-directory, path/file/entrypoint keys
- Dockerfiles: COPY/ADD source paths, recursive scan, multi-context check
- Skips: remote actions, globs, variables, absolute/tilde paths, --from=stage
- 32 tests, reviewer findings fixed (tilde/absolute FP, recursive Dockerfiles)

#### Inline comment drift detector (Session 40)
- New `inline-comment-drift` LLM-assisted detector (docs-drift category)
- Python AST extraction of (docstring, code body) pairs
- Binary LLM prompt with basic/enhanced mode (ADR-016)
- Risk-based file sorting via churn signals (TD-043)
- Per-file (20) and per-scan (100) LLM call limits
- 24 tests, reviewer findings fixed (risk signal keys, VISION-LOCK version)

#### Architecture drift detector (Session 40)
- New `architecture-drift` deterministic detector (config-drift category)
- Rules in `[sentinel.architecture]` section of sentinel.toml
- Layer ordering, shared module exemptions, forbidden imports
- AST import graph with relative import resolution
- 43 tests, reviewer findings fixed (relative imports, evidence type, doc labels)

#### Docs updated
- VISION-LOCK v5.5: 17 detectors, Phase 10 3/4 shipped, changelog pruned
- detector-interface.md: 3 new rows, stale entries removed, date updated
- overview.md: detector list updated, date updated
- compatibility-matrix.md: 14 deterministic + inline-comment-drift section
- README.md: 17 detectors, test count updated

### Repository State
- **Tests**: 1235 passing, 3 skipped
- **VISION-LOCK**: v5.5
- **Tech debt items**: 10 active
- **Open questions**: 2 partially resolved (OQ-009, OQ-019), 2 open (OQ-006, OQ-016)
- **ADRs**: 16
- **Detectors**: 17 (was 14)
- **Commits this session**: 6

### What Remains / Next Priority
1. **Phase 10 remaining** — intent comparison (multi-artifact triangulation)
2. **Benchmark DB integration** — make `sentinel benchmark` write to `llm_log` for full drill-down
3. **OQ-016 (low)** — message list protocol evolution

---

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
