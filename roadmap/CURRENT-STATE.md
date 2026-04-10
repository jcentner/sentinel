# Current State — Sentinel

> Last updated: Session 29 — Comprehensive detector report delivered

## Latest Session Summary

### Current Objective
Deliver comprehensive detector report based on multi-repo validation data from Session 28.

### What Was Accomplished

#### Comprehensive detector report delivered
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

#### Known issues to address
1. **Dead-code JS/TS monorepo FPs** — 1692 FPs on shadcn-ui from non-auto-generated files with dynamic consumption patterns. Needs cross-package import tracking and runtime-resolved import resolution.
2. **Docs-drift edge-case FPs** — 2 remaining on pip-tools (CHANGELOG feature descriptions), 6 on shadcn-ui (user-project paths in template repos).
3. **Complexity test-file noise** — ~50% of complexity findings are in test files (accurate but low-value). May benefit from `--skip-tests` filter or reduced severity.

#### Next priorities
1. **LLM detector validation** — Exercise `semantic-drift` and `test-coherence` with Ollama provider on a real repo
2. **PyPI publication** — Package and publish
3. **Full-pipeline scan** — Run against a repo with LLM enabled to validate judge + synthesis + report end-to-end
4. **Phase 10 planning** — Advanced detectors based on validation lessons learned

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
