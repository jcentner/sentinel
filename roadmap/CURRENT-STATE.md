# Current State — Sentinel

> Last updated: Session 37 — Benchmark-driven model quality (ADR-016)

**Phase Status**: In Progress

## Latest Session Summary

### Current Objective
Replace the tier-based model taxonomy with benchmark-driven model quality (ADR-016). Separate prompt strategy, quality ratings, and recommendations into independent concerns.

### What Was Accomplished

#### ADR-016: Benchmark-driven model quality (Session 37)
- **New ADR-016**: Supersedes ADR-011 tier system. Three concerns separated:
  1. **Prompt strategy** — binary vs enhanced, driven by benchmark data (not tier label)
  2. **Quality ratings** — empirical per-model×detector, reference benchmarks shipped
  3. **Recommendations** — editorial advice by user situation, not computed taxonomy
- **`should_use_enhanced_prompt()`** in compatibility.py — checks enhanced-mode (standard-tier) quality first, falls back to `model_capability` config hint, defaults to binary (safe for any model)
- **`model_name_to_class()`** — substring matching for known models (longest-key-first to avoid ambiguity)
- **`get_reference_quality()` / `get_enhanced_quality()`** — separate lookups for basic and enhanced mode
- **Both LLM detectors updated** — semantic-drift and test-coherence now call `should_use_enhanced_prompt()` instead of inline `model_cap in (STANDARD, ADVANCED)` check
- **28 new tests** covering model mapping, quality lookup, prompt strategy edge cases — 1109 total
- **Reviewer-driven fixes**: overview.md stale tier references, direct `get_enhanced_quality()` tests, model name edge cases

#### Docs updated
- VISION-LOCK v5.2: tier-centric → benchmark-driven language
- ADR-011 status → Superseded by ADR-016
- ADR index updated with ADR-016
- copilot-instructions.md: quality standards updated
- compatibility-matrix.md: recommendations table replaces fixed model class taxonomy
- glossary: capability tier definition updated
- overview.md: tier references → ADR-016 references
- OQ-019: benchmark drill-down UI for power users (new open question)
- TD-032: updated to reference ADR-016 for synthesis gating

#### Key design insight
Enhanced (standard-tier) mode quality must be checked separately from basic-mode quality. A model can have GOOD quality at basic tier (binary prompts) but UNTESTED at standard tier (enhanced prompts). Currently all standard-tier entries are UNTESTED, so the benchmark check is forward-looking infrastructure — for now, `model_capability` config hint drives the decision.

#### Files modified
- `docs/architecture/decisions/016-benchmark-driven-model-quality.md` — new ADR
- `docs/architecture/decisions/011-capability-tier-system.md` — status → Superseded
- `docs/architecture/decisions/README.md` — ADR index
- `docs/architecture/overview.md` — stale tier refs
- `docs/vision/VISION-LOCK.md` — v5.2
- `docs/reference/compatibility-matrix.md` — recommendations table
- `docs/reference/glossary.md` — capability tier
- `docs/reference/open-questions.md` — OQ-019
- `docs/reference/tech-debt.md` — TD-032
- `.github/copilot-instructions.md` — quality standards
- `src/sentinel/core/compatibility.py` — 4 new functions
- `src/sentinel/detectors/semantic_drift.py` — benchmark-driven prompt strategy
- `src/sentinel/detectors/test_coherence.py` — benchmark-driven prompt strategy
- `tests/test_benchmark.py` — 28 new tests

### Repository State
- **Tests**: 1109 passing, 3 skipped
- **VISION-LOCK**: v5.2
- **Tech debt items**: 13 active
- **Open questions**: 19 total, 16 resolved, 3 remaining (OQ-006, OQ-016, OQ-019)
- **ADRs**: 16
- **Commits this session**: 2

### What Remains / Next Priority
1. **Web UI updates** — matrix display should reflect ADR-016 approach (dynamic model columns from benchmark data rather than fixed taxonomy)
2. **Benchmark drill-down** (OQ-019) — let power users inspect actual prompts/outputs per benchmark run
3. **README pruning** (TD-055) — delegate to wiki, target <150 lines
4. **Roadmap phases cleanup** (TD-053) — archive stale phases/

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
