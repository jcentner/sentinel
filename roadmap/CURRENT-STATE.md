# Current State — Sentinel

> Last updated: Session 38 — ADR-016 web UI + doc health

**Phase Status**: Complete

## Latest Session Summary

### Current Objective
Continue ADR-016 rollout: update web UI, resolve document health tech debt (TD-053, TD-055).

### What Was Accomplished

#### Web UI matrix updated for ADR-016 (Session 38)
- Matrix column headers show actual model names (`qwen3.5:4b`, `gpt-5.4-nano`) with Local/Cloud labels instead of arbitrary class names with tier badges
- "Model Classes" taxonomy table replaced by "Recommendations by Situation" (practical advice by VRAM/budget scenario)
- "Benchmarked Models" reference table replaces the old fixed taxonomy
- ADR-016 link and `sentinel benchmark` prompt in descriptive text

#### README pruned — TD-055 resolved
- 404 → 112 lines (target was <150)
- Moved to wiki: full CLI reference, web UI feature list, scheduling, custom detectors, config details, machine-readable output, AI agent integration
- Kept: problem statement, what-it-does (compact), quick start, key commands table, minimal config, docs links, dev setup

#### Roadmap cleanup — TD-053 resolved
- Archived `roadmap/phases/` to `roadmap/archive/phases/`
- Updated `roadmap/README.md`: all phases complete, future work is slice-based
- Both TD-053 and TD-055 moved to tech-debt-resolved.md

#### Files modified
- `src/sentinel/web/templates/compatibility.html` — matrix reframing for ADR-016
- `README.md` — pruned from 404 to 112 lines
- `roadmap/README.md` — all phases complete, slice-based future
- `roadmap/phases/` → `roadmap/archive/phases/`
- `docs/reference/tech-debt.md` — removed TD-053, TD-055
- `docs/reference/tech-debt-resolved.md` — added TD-053, TD-055

### Repository State
- **Tests**: 1109 passing, 3 skipped
- **VISION-LOCK**: v5.2
- **Tech debt items**: 11 active (was 13 — resolved TD-053, TD-055)
- **Open questions**: 19 total, 16 resolved, 3 remaining (OQ-006, OQ-016, OQ-019)
- **ADRs**: 16
- **Commits this session**: 3

### What Remains / Next Priority
1. **Benchmark drill-down** (OQ-019) — power user UI to inspect actual prompts/outputs per benchmark run
2. **Cross-detector data flow** (TD-043) — git-hotspots → LLM targeting
3. **Index management page** — web equivalent of `sentinel index`

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
