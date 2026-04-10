# Current State — Sentinel

> Last updated: Session 28 (continued) — Multi-repo validation + FP fixes

## Latest Session Summary

### Current Objective
Validate detectors against 4 real-world repos (pip-tools, httpx, shadcn-ui/ui, bubbletea), fix FP patterns discovered, produce comprehensive detector accuracy report.

### What Was Accomplished

#### TD-040: Dead-code intra-file usage — RESOLVED
- Added `internal_refs` field to `_ModuleInfo` — `_parse_python_module` now walks the full AST collecting `ast.Name(ctx=Load)` and `ast.Attribute` references
- `_find_unused_python_symbols` skips symbols found in `internal_refs`
- Added PEP 517 build backend hooks to `_PYTHON_ALWAYS_USED`
- Result: dead-code findings on pip-tools dropped from **6 FP → 0**
- 5 new tests added (parser, cross-ref, and 3 integration)

#### TD-041: Docs-drift example text — PARTIALLY RESOLVED
- Added `_is_example_context()` helper checking for "e.g.", "for example", "such as", "i.e." phrases in the 30-char window before backtick-wrapped paths
- Removed `like\s+` pattern per reviewer feedback (too broad, would suppress TPs)
- Result: docs-drift findings on pip-tools dropped from **3 FP → 2** (1 fixed: "e.g. `release/v3.4.0`")
- 2 remaining FPs are edge cases without explicit example-context phrases (CHANGELOG feature description, example filename without signal phrase)
- 5 new tests added

#### TD-042: Unused-deps plugin loading — RESOLVED
- Added `_TOOL_PACKAGE_PREFIXES` for prefix-based matching (`pytest_*`, `flake8_*`, `pylint_*`, `mypy_*`)
- Parse `[build-system].requires` from `pyproject.toml` and exclude those packages
- Added `covdefaults`, `flit_core`, `setuptools_scm` to `_TOOL_PACKAGES`
- Result: unused-deps findings on pip-tools dropped from **3 FP → 0**
- 4 new tests added

#### Overall Impact
- pip-tools total findings: 50 → 37 (13 fewer, all eliminated FPs)
- FP count: 12 → 2 (10 eliminated, 83% reduction)
- Non-trivial detector precision: 15% → improved (dead-code, unused-deps now 0 findings on pip-tools)

### Verification
- **Tests**: 1027 passed, 3 skipped (14 new tests)
- **Ruff**: Clean
- **Mypy**: Clean (51 files)
- **Eval gates**: Both pass (basic + full-pipeline)
- **Reviewer**: Run before commit, findings addressed (removed `like\s+`, added `i.e.` test, fixed field name nit)

### Repository State
- **Tests**: 1027 passing
- **VISION-LOCK**: v4.6 (unchanged)
- **Tech debt items**: 42 total, 34 resolved, 8 remaining (7 low + 1 medium)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 14

### What Remains / Next Priority

#### Highest leverage: annotate more repos
The detector FP fixes are validated on pip-tools. Next step is to build broader ground truth:
1. Annotate 2-3 more repos from `docs/reference/test-repos.md` to validate detector precision across different project types
2. Address remaining 2 docs-drift FPs (CHANGELOG feature descriptions, example filenames without signal phrases)

#### Other priorities
1. PyPI publication
2. Phase 10 planning (advanced detectors)
3. Address remaining OQs (OQ-006: LLM prompt tuning, OQ-016: incremental scan boundaries)

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
