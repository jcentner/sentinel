# Current State — Sentinel

> Last updated: Session 29 (continued) — Quick fixes + wiki planning

## Latest Session Summary

### Current Objective
Apply learnings from detector analysis, decouple skip-judge/skip-llm, plan GitHub wiki.

### What Was Accomplished

#### Quick fixes from detector analysis
1. **Decoupled `--skip-judge` from `--skip-llm`** — New `--skip-llm` CLI flag and `skip_llm` config field. `--skip-judge` now only controls the judge step; LLM-assisted detectors (semantic-drift, test-coherence) can run independently.
2. **Complexity test-file demotion** — Complex functions in test files now get `LOW` severity and `0.60` confidence (down from computed severity and `0.95`). Same detection, lower report noise.
3. **New tech debt items** — TD-043 (cross-detector data flow for LLM targeting), TD-044 (dead-code JS monorepo FPs), TD-045 (ground truth size).

#### GitHub wiki planned
- 24-page structure designed: landing page, setup, CLI reference, per-detector pages, provider config, scheduling, etc.
- Each detector gets its own wiki page with: what it detects, tier, languages, tools, LLM needs, config, example, limitations, accuracy.
- **Blocked on**: user needs to enable Wikis in GitHub repo settings first.

#### Comprehensive detector report delivered (earlier this session)
- Covered all 14 detectors with: conceptual design, accuracy data, value estimation, LLM requirements, and real examples
- Based on validation against 4 real-world repos: pip-tools (Python), httpx (Python), shadcn-ui/ui (JS/TS monorepo), bubbletea (Go)

#### Multi-repo validation results (Session 28, summarized)

| Repo | Total | Key Findings |
|------|-------|-------------|
| pip-tools | 37 | 20 complexity, 19 todo (all TP), 2 docs-drift FP |
| httpx | 36 | 31 complexity, 3 dep-audit (real CVEs), 1 docs-drift TP, 1 todo |
| shadcn-ui | 1720 | 1692 dead-code (~99% FP — JS monorepo dynamic imports), 20 todo TP, 8 docs-drift |
| bubbletea | 8 | 8 todo (all TP) |

#### Detector accuracy summary

| Detector | Observed TP Rate | Value | LLM Required |
|----------|-----------------|-------|-------------|
| todo-scanner | 100% | Medium-High | No |
| dep-audit | 100% | High | No (needs pip-audit) |
| lint-runner | 100% | High | No (needs ruff) |
| complexity | ~95% | Medium | No |
| unused-deps | ~90%+ | High | No |
| dead-code (Python) | ~100% | Medium | No |
| dead-code (JS/TS) | ~1% | Low (monorepo noise) | No |
| docs-drift | 50-100% varies | Medium-High | Optional |
| stale-env | 0 findings tested | Medium (niche) | No |
| git-hotspots | Not tested (shallow clones) | Medium-High | No |
| semantic-drift | Not tested (skip-judge) | Potentially High | Yes (BASIC) |
| test-coherence | Not tested (skip-judge) | Potentially High | Yes (BASIC) |
| eslint-runner | Not tested (no tool) | High | No (needs biome/eslint) |
| go-linter | Not tested (no tool) | High | No (needs golangci-lint) |
| rust-clippy | Not tested (no tool) | High | No (needs cargo clippy) |

### Repository State
- **Tests**: 1034 passing
- **VISION-LOCK**: v4.6 (unchanged)
- **Tech debt items**: 42 total, 34 resolved, 8 remaining (7 low + 1 medium)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 14

### What Remains / Next Priority

#### Immediate: GitHub wiki
1. User enables wiki in GitHub repo settings
2. Agent populates wiki with 24 pages from existing detector data

#### Next priorities
1. **LLM detector validation** — Run semantic-drift and test-coherence with Ollama (now possible with `--skip-judge` without `--skip-llm`)
2. **Full-pipeline scan** — Validate judge + synthesis + report end-to-end
3. **PyPI publication** — Package and publish
4. **Cross-detector data flow** (TD-043) — Let git-hotspots inform LLM detector targeting

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
