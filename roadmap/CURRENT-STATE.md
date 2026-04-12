# Current State — Sentinel

> Last updated: Session 39 — LLM call log viewer

**Phase Status**: In Progress

## Latest Session Summary

### Current Objective
Build the LLM call log viewer (OQ-019 partial), then continue with the next highest-leverage slices.

### What Was Accomplished

#### LLM call log viewer (Session 39)
- New `/llm-log` page with full drill-down: prompts, responses, verdicts, timing
- Filters: detector, model, verdict, run ID
- Pagination (50 per page)
- Expandable `<details>` for prompt and response text
- Verdict badges, timing (ms), token counts per call
- Linked from nav bar and detectors page
- Store: `get_llm_log_entries()` and `get_llm_log_filters()` in `llm_log.py`
- OQ-019 updated to Partially Resolved
- 18 new tests (10 web route, 8 store)

#### Files modified
- `src/sentinel/store/llm_log.py` — `get_llm_log_entries()`, `get_llm_log_filters()`
- `src/sentinel/web/routes/llm_log.py` — new route handler
- `src/sentinel/web/templates/llm_log.html` — new template
- `src/sentinel/web/app.py` — route registration
- `src/sentinel/web/templates/base.html` — nav link
- `src/sentinel/web/templates/compatibility.html` — cross-link
- `docs/reference/open-questions.md` — OQ-019 partially resolved
- `tests/test_web.py` — 10 new tests
- `tests/test_llm_log.py` — 8 new tests

### Repository State
- **Tests**: 1127 passing, 3 skipped
- **VISION-LOCK**: v5.2
- **Tech debt items**: 11 active
- **Open questions**: 19 total, 16 resolved, 2 partially resolved (OQ-009, OQ-019), 1 open (OQ-006)
- **ADRs**: 16
- **Commits this session**: 2 (checkpoint + LLM log viewer)

### What Remains / Next Priority
1. **Cross-detector data flow** (TD-043) — git-hotspots → LLM targeting
2. **Index management page** — web equivalent of `sentinel index`
3. **Benchmark DB integration** — make `sentinel benchmark` write to `llm_log` for drill-down
4. **Advanced detectors** (Phase 10) — CI/CD config drift, inline comment drift

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
- **Sessions 37-38**: ADR-016 benchmark-driven quality, web UI matrix, README pruning, roadmap cleanup

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
