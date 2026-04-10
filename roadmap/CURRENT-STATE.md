# Current State — Sentinel

> Last updated: Session 27 — UX improvements, AI consumability, value prop refinement

## Latest Session Summary

### Current Objective
Address user feedback: auto-open browser on `sentinel serve`, curated test repos, AI agent integration (SKILL.md), competitive analysis refresh, and open questions for OAuth and GitHub wiki.

### What Was Accomplished

#### `sentinel serve --open` (auto-open browser)
- Added `--open/--no-open` flag to the serve command (default: open)
- Uses `threading.Timer` + `webbrowser.open` to open browser after 1s delay (lets uvicorn start first)
- All 81 CLI + GitHub tests pass

#### Curated test repos for validation
- Created `docs/reference/test-repos.md` with 13 recommended public repos across Python, JS/TS, Go, Rust, and multi-language categories
- Each repo has selection rationale and key detectors to exercise
- Includes quick-start commands and validation workflow

#### AI consumability (SKILL.md)
- Created `.github/skills/setup-sentinel/SKILL.md` — a Copilot skill for AI-assisted setup
- Covers installation, init profiles, language-specific detector configs, model provider setup, scheduling
- Updated README with "AI Agent Integration" section documenting `--json-output`, exit codes, quiet mode, and the skill

#### Competitive analysis refresh
- Rewrote `docs/analysis/competitive-landscape.md` with the blog post's value proposition framing
- Added "The core problem nobody else solves" section — cross-artifact drift from fast AI-assisted development
- Added "The observed differentiator" section with real-world validation data (88% confirmation rate, 100% docs-drift accuracy)
- Updated gap list to include AI-agent integration as differentiator #7

#### Open questions recorded
- **OQ-017**: Should GitHub integration support OAuth device flow? (Medium priority, current thinking: both PAT + OAuth)
- **OQ-018**: Should project docs live in the GitHub wiki? (Low priority, current thinking: hybrid — in-repo for dev docs, wiki for user guides)

### Verification
- **Tests**: 81 passed (CLI + GitHub tests) — broader suite not re-run (no core logic changes)
- **Ruff**: Clean on modified files
- **Import check**: CLI module imports cleanly

### Repository State
- **Tests**: 1013 passing (no regressions expected — only CLI UX change)
- **VISION-LOCK**: v4.6 (unchanged)
- **Open questions**: 18 total, 13 resolved, 5 remaining (OQ-006, OQ-014, OQ-016, OQ-017, OQ-018)

### Files Modified This Session
- `src/sentinel/cli.py` — serve command `--open/--no-open` flag
- `docs/reference/test-repos.md` — new: curated test repos
- `.github/skills/setup-sentinel/SKILL.md` — new: Copilot setup skill
- `docs/analysis/competitive-landscape.md` — rewritten with blog value props
- `docs/reference/open-questions.md` — added OQ-017 (OAuth), OQ-018 (wiki)
- `README.md` — added AI Agent Integration section, test repos link
- `roadmap/CURRENT-STATE.md` — this file

### What Remains / Next Priority

#### User's deferred items
1. **Real-world repo testing**: Clone repos from test-repos.md and run Sentinel scans to validate
2. **OQ-017 resolution**: Decide on OAuth device flow (needs human input on GitHub App registration cost/benefit)
3. **OQ-018 resolution**: Decide on GitHub wiki usage (needs human input on target audience)
4. **GitHub issue creation end-to-end test**: Run `sentinel create-issues --dry-run` against a real repo with approved findings

#### Remaining from Session 26
1. **Stale samples**: samples/ directory has report and JSON from Session 8; regenerate
2. **PyPI publication**: Release workflow exists, needs `pypi` environment in GitHub settings, tag v0.1.0
3. **OQ-014 resolution**: Requires human decision on ground truth corpus strategy

---

## Previous Sessions (Archived)

Session summaries for Sessions 1–24 are preserved in git history. Key milestones:

- **Sessions 1–3**: Vision lock, Phase 1 plan, core pipeline (detectors → fingerprint → dedup → judge → report)
- **Sessions 7–8**: Web UI, SQLite store, CLI commands, sample repo fixture
- **Sessions 10–13**: Provider abstraction, embedding-based context, incremental scanning
- **Sessions 15–19**: Advanced detectors, eval system, clustering, synthesis
- **Sessions 20–22**: Per-detector providers (ADR-013), benchmarking system, sample repo expansion
- **Sessions 23–24**: Systemic review — resolved 25/26 tech debt items (TD-013 through TD-038)
- **Session 25**: Full-pipeline eval with replay provider (OQ-013, ADR-014)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
