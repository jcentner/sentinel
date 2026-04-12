# Current State — Sentinel

> Last updated: Session 39 — LLM log viewer + cross-detector data flow + embed index page

**Phase Status**: In Progress

## Latest Session Summary

### Current Objective
Build LLM call log viewer (OQ-019 partial), cross-detector data flow (TD-043), and embedding index page.

### What Was Accomplished

#### LLM call log viewer (Session 39)
- New `/llm-log` page: prompts, responses, verdicts, timing with drill-down
- Filters: detector, model, verdict, run ID + pagination (50/page)
- Linked from nav bar and detectors page
- Store: `get_llm_log_entries()` and `get_llm_log_filters()` in `llm_log.py`
- OQ-019 updated to Partially Resolved
- 18 new tests (10 web route, 8 store)

#### Cross-detector data flow — TD-043 resolved (Session 39)
- Two-phase execution in runner: heuristic/deterministic first, LLM second
- `_build_risk_signals()` extracts structured signals from git-hotspots
- `DetectorContext.risk_signals` field propagated to LLM detectors
- git-hotspots: structured `context` dict (churn_commits, fix_ratio, etc.)
- test-coherence: sorts test files by implementation risk score
- 7 new tests, all docs updated (detector-interface, overview, VISION-LOCK v5.3)
- TD-043 moved to tech-debt-resolved

#### Embedding index page (Session 39)
- New `/embed-index` page: file count, chunk count, embed model
- Linked from doctor page
- 2 new tests
- VISION-LOCK: Web UI first-class interaction surface marked complete

#### Files modified
- `src/sentinel/store/llm_log.py` — new query functions
- `src/sentinel/web/routes/llm_log.py` — new route
- `src/sentinel/web/templates/llm_log.html` — new template
- `src/sentinel/web/routes/index.py` — new route (embed index)
- `src/sentinel/web/templates/embed_index.html` — new template
- `src/sentinel/web/app.py` — route registration
- `src/sentinel/web/templates/base.html` — nav link
- `src/sentinel/web/templates/compatibility.html` — cross-link
- `src/sentinel/web/templates/doctor.html` — embed index link
- `src/sentinel/core/runner.py` — two-phase execution, risk signals
- `src/sentinel/detectors/git_hotspots.py` — structured context
- `src/sentinel/detectors/test_coherence.py` — risk-based sorting
- `src/sentinel/models.py` — risk_signals on DetectorContext
- `docs/architecture/detector-interface.md` — risk_signals field
- `docs/architecture/overview.md` — two-phase pipeline
- `docs/vision/VISION-LOCK.md` — v5.3, web UI complete
- `docs/reference/tech-debt.md` — TD-043 removed
- `docs/reference/tech-debt-resolved.md` — TD-043 added
- `docs/reference/open-questions.md` — OQ-019 partially resolved

### Repository State
- **Tests**: 1136 passing, 3 skipped
- **VISION-LOCK**: v5.3
- **Tech debt items**: 10 active
- **Open questions**: 2 partially resolved (OQ-009, OQ-019), 2 open (OQ-006, OQ-016)
- **ADRs**: 16
- **Commits this session**: 6

### What Remains / Next Priority
1. **Benchmark DB integration** — make `sentinel benchmark` write to `llm_log` for full drill-down
2. **Advanced detectors** (Phase 10) — CI/CD config drift, inline comment drift
3. **OQ-016 (low)** — message list protocol evolution

---

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
