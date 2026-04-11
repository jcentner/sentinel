# Current State — Sentinel

> Last updated: Session 35 — Web UI first-class interaction surface

**Phase Status**: In Progress

## Latest Session Summary

### Current Objective
Make the web UI a first-class interaction surface (ADR-015). Users landing in the browser should be able to discover, configure, and operate Sentinel without leaving the web UI.

### What Was Accomplished

#### Web UI first-class interaction (Session 35 — ADR-015)
- **ADR-015**: Recorded decision — web UI is a first-class interaction surface, not a read-only dashboard
- **Config write layer**: `save_config()` in config.py — atomic TOML write, manual serialization (no new deps), only writes non-default values
- **Route split**: app.py 796→101 lines. 7 route modules in `web/routes/` + `web/shared.py` for templates/DB helpers
- **Settings page**: Rewritten as editable form — creates/updates sentinel.toml. Groups: Model & Provider, Embeddings, Pipeline, Detectors, Paths. Success toast, field validation.
- **Nav rename**: Compatibility → Detectors (both `/detectors` and `/compatibility` routes work)
- **TD-048 fix**: Scan form "LLM Model" → "Model" with accurate hint
- **TD-049 fix**: Deterministic detectors collapsed to summary with expandable `<details>`
- **TD-050 partial**: Added hardware speed caveat to Model Classes table
- **TD-051 fix**: Claude Sonnet 4 → 4.6 in compatibility.py
- **Tech debt**: 6 items resolved (TD-046,048,049,050,051,052), TD-047 updated to deliberate/low-pri
- **VISION-LOCK v5.1**: Dual interface constraint refined, "Where We're Going" updated

#### Files created
- `docs/architecture/decisions/015-web-ui-first-class-interface.md`
- `src/sentinel/web/shared.py`
- `src/sentinel/web/routes/__init__.py`
- `src/sentinel/web/routes/` — findings.py, runs.py, scan.py, settings.py, detectors.py, eval.py, github.py

#### Files modified
- `src/sentinel/web/app.py` — slimmed to factory + index (796→101 lines)
- `src/sentinel/config.py` — added save_config(), _toml_value()
- `src/sentinel/core/compatibility.py` — Sonnet 4 → 4.6
- `src/sentinel/web/templates/settings.html` — editable form
- `src/sentinel/web/templates/base.html` — Detectors nav
- `src/sentinel/web/templates/compatibility.html` — collapsed deterministic section + speed caveat
- `src/sentinel/web/templates/scan.html` — model label fix
- `tests/test_web.py` — 6 new settings save tests, updated assertions

### Repository State
- **Tests**: 1052 passing + 6 new = 1058+ (pending full count), 3 skipped
- **VISION-LOCK**: v5.1
- **PyPI**: `repo-sentinel` v0.1.0 published
- **Tech debt items**: 13 active (was 19; 6 resolved)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 15

### What Remains / Next Priority

#### Immediate
1. **Detectors page config** — inline detector toggles + per-detector model selection on the Detectors page (continuation of ADR-015)
2. **Doctor page** — web equivalent of `sentinel doctor` health check
3. **README pruning** (TD-055) — delegate to wiki, target <150 lines

#### Next feature priorities
1. **Roadmap phases cleanup** (TD-053) — archive stale phases/
2. **Cross-detector data flow** (TD-043) — git-hotspots → LLM targeting
3. **Index management page** — web equivalent of `sentinel index`

#### Deprioritized
- Async judge (TD-016) — low priority, design runs in background
- GitHub config editing (TD-047) — token must stay env-var, owner/repo low value

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
