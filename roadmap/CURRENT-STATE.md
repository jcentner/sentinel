# Current State — Sentinel

> Last updated: Session 36 — Web UI UX refinement

**Phase Status**: Complete

## Latest Session Summary

### Current Objective
Refine the web UI based on user testing feedback — fix discoverability, naming confusion, and missing features across all pages.

### What Was Accomplished

#### Detectors page UX overhaul (Session 36)
- **Tier badges in matrix headers**: Each model class column now shows its capability tier (basic/standard/advanced) under the name, connecting matrix ratings to config settings
- **"Your Measured Speed" column**: Model Classes table shows actual tok/s from scan data per model, aggregated from `llm_log`. Shows "After first scan" placeholder when no data exists. Handles multi-model classes (e.g., "gpt-5.4-mini, Claude Haiku 4.5") via weighted average.
- **Language column for Other Detectors**: Replaced collapsed deterministic section with "Other Detectors" table showing language column (Python, JS/TS, Go, Rust, Any)
- **Inline rating legend**: Moved from separate card to compact inline footer within LLM table
- **"(global)" → "(default)"**: All config dropdowns and override text now say "(default)" to clarify fallback hierarchy

#### Cross-page improvements
- **Settings hierarchy hint**: "Per-detector overrides on the Detectors page take precedence over these defaults"
- **Model datalists**: Settings + Scan pages now offer autocomplete suggestions for model and embedding model inputs (qwen3.5:4b, gpt-5.4-nano, nomic-embed-text, etc.)
- **GitHub Issues CSRF**: Added missing CSRF tokens to both Create Issues and Dry Run forms
- **Env var disclaimer**: GitHub + Settings pages now explain env vars must be set outside Sentinel
- **Doctor defaults fix**: sentinel.toml check now says "Using defaults (provider=..., model=...)" when no file exists
- **Embed model hints**: "Local Ollama embedding models are fast and sufficient — no cloud needed"

#### Infrastructure
- `get_model_speed_stats()` in `store/llm_log.py` — per-model tok/s aggregation from LLM log, excludes NULL/zero rows
- Model class speed mapping in `/detectors` route — maps per-model stats to model class IDs via example model matching
- 3 new tests for model speed stats (empty, multi-model, null exclusion)

#### Files modified
- `src/sentinel/core/compatibility.py` — added `language` field to all 14 DETECTOR_INFO entries
- `src/sentinel/core/doctor.py` — sentinel.toml defaults check
- `src/sentinel/store/llm_log.py` — `get_model_speed_stats()`
- `src/sentinel/web/routes/detectors.py` — model speed wiring, import fix
- `src/sentinel/web/templates/compatibility.html` — major rewrite
- `src/sentinel/web/templates/github.html` — CSRF + disclaimer
- `src/sentinel/web/templates/settings.html` — hierarchy hint + datalists
- `src/sentinel/web/templates/scan.html` — datalists + "default" labels
- `tests/test_llm_log.py` — model speed tests

### Repository State
- **Tests**: 1069 passing, 3 skipped
- **VISION-LOCK**: v5.1
- **Tech debt items**: 13 active
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 15
- **Commits this session**: 1

### What Remains / Next Priority
1. **README pruning** (TD-055) — delegate to wiki, target <150 lines
2. **Roadmap phases cleanup** (TD-053) — archive stale phases/
3. **Cross-detector data flow** (TD-043) — git-hotspots → LLM targeting
4. **Index management page** — web equivalent of `sentinel index`

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
