# Current State — Sentinel

> Last updated: Session 30 — PyPI published, public launch ready

## Latest Session Summary

### Current Objective
Prepare for public launch: PyPI publication, packaging fixes, from-scratch install verification.

### What Was Accomplished

#### PyPI publication — `repo-sentinel` v0.1.0 live
- Package published at https://pypi.org/project/repo-sentinel/
- `pip install repo-sentinel` verified in clean venv: install → `sentinel --version` → `sentinel doctor` → `sentinel init` → `sentinel scan` all work
- Extras verified: `[detectors]` (ruff, pip-audit), `[web]` (starlette, jinja2, uvicorn)
- Trusted publishing configured via GitHub Actions release workflow on `v*` tags

#### Launch preparation fixes
1. **Package name**: renamed from `local-repo-sentinel` to `repo-sentinel` for memorability
2. **Install instructions**: added `pip install repo-sentinel` as primary install path in README, fixed all `pip install sentinel[web]` → `pip install "repo-sentinel[web]"` across README, cli.py, overview.md, SKILL.md, CONTRIBUTING.md
3. **Authors field**: added to pyproject.toml (`Jacob Centner <contact@write-it-right.ai>`)
4. **py.typed marker** (PEP 561): added for type checker support, included in package-data
5. **scratch.md**: removed from git tracking, added to .gitignore (contained personal brainstorm notes)
6. **Git clone URL**: replaced `<repo-url>` placeholder with `https://github.com/jcentner/sentinel.git` in README and CONTRIBUTING
7. **VISION-LOCK**: bumped to v4.7. PyPI publication marked complete.

#### Verification
- 1035 tests passing, ruff + mypy strict clean
- Clean build: sdist (208KB) + wheel (193KB)
- Wheel contents verified: all 51 source files, 12 templates, 3 static files, py.typed, LICENSE
- From-scratch install tested in clean venv from built wheel and from PyPI

### Repository State
- **Tests**: 1035 passing
- **VISION-LOCK**: v4.7
- **PyPI**: `repo-sentinel` v0.1.0 published
- **Tech debt items**: 42 total, 34 resolved, 8 remaining (7 low + 1 medium)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 14

### What Remains / Next Priority

#### Next priorities
1. **LLM detector validation** — Run semantic-drift and test-coherence with a model provider (now possible with `--skip-judge` without `--skip-llm`)
2. **Full-pipeline scan** — Validate judge + synthesis + report end-to-end
3. **Cross-detector data flow** (TD-043) — Let git-hotspots inform LLM detector targeting
4. **Wiki maintenance** — Keep wiki in sync with code changes

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
