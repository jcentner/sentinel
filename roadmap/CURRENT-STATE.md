# Current State — Sentinel

> Last updated: Session 32 — Full-pipeline validation, compatibility matrix, real-world scans

## Latest Session Summary

### Current Objective
Full-pipeline E2E validation, test-coherence prompt refinement, real-world repo scanning, and model-detector compatibility matrix feature.

### What Was Accomplished

#### Full-pipeline E2E validation
- Ran `sentinel scan tests/fixtures/sample-repo --model qwen3.5:4b --capability standard` — 35 findings, judge confirmed 30, rejected 5. Full morning report generated with evidence, judge reasoning, and clusters.
- Ran `sentinel eval tests/fixtures/sample-repo --full-pipeline` — P=89%, R=100%. Judge correctly identified test fixture hints (not a real quality issue).

#### Test-coherence prompt refinement
- Refined basic and enhanced test-coherence prompts with explicit "coherent patterns" guidance (CLI runners, mocked external deps, simple tests).
- Self-scan FPs dropped from 14 → 7 (~50% reduction).

#### LLM detector ground truth
- Added 3 ground truth entries to sample-repo (1 semantic-drift, 2 test-coherence).
- Fixed eval to only count expected entries from detectors that actually ran (prevents LLM ground truth from penalizing recall in non-full-pipeline mode).

#### Real-world validation — two external repos
- **tsgbuilder** (Python CLI): 113 raw → 101 dedup → 93 confirmed. Test-coherence found 4 findings (all FPs on well-written edge-case tests in test_telemetry.py).
- **wyoclear** (Next.js): 202 raw → 168 dedup → 152 confirmed. 58 dead-code, 73 docs-drift. Synthesis produced 5 clusters.

#### Model-detector compatibility matrix (major feature)
- Created `src/sentinel/core/compatibility.py` — authoritative data module with QualityRating enum, CompatibilityEntry dataclass, full matrix data for 14 detectors + judge × 4 model classes, query helpers (get_entry, get_detector_recommendation, build_summary_table).
- Created `docs/reference/compatibility-matrix.md` — wiki documentation with rating legend, LLM-assisted detector matrix, judge quality table, recommended configurations, model classes reference.
- Created `/compatibility` web UI page with color-coded quality badges (excellent/good/fair/poor).
- Added scan page dynamic warnings — JS shows "⚠ test-coherence has ~40% FP rate with 4B local models" when poor combos selected.
- Updated Vision lock to v4.8 — new "Model-detector transparency" product constraint.
- Updated copilot-instructions.md with compatibility-matrix.md link and transparency quality standard.
- Added 3 glossary terms: Compatibility matrix, Quality rating, Model class.
- 4 new web tests for compatibility page (86 total web tests).
- mypy strict clean.

#### Commits this session
- `b8248f5` — docs(benchmarks): LLM detector validation results and pytest config fix
- `8d8501b` — fix(detectors): test-coherence prompt refinement (14→7 FPs)
- `5d882a8` — feat(eval): LLM detector ground truth, eval active_expected fix
- `730da4f` — feat(compatibility): model-detector compatibility matrix (11 files, +815 lines)
- `09ecdce` — fix(compatibility): mypy strict type args

### Repository State
- **Tests**: 1046 passing, 3 skipped
- **VISION-LOCK**: v4.8
- **PyPI**: `repo-sentinel` v0.1.0 published
- **Tech debt items**: 42 total, 35 resolved, 7 remaining (6 low + 1 medium)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 14

### What Remains / Next Priority

#### Next priorities
1. **Cross-detector data flow** (TD-043) — Let git-hotspots inform LLM detector targeting
2. **Async judge** (TD-016) — ThreadPoolExecutor-based parallel judging (~4x speedup)
3. **`sentinel compatibility` CLI command** — Print compatibility matrix to terminal (glossary references it but not yet implemented)
4. **wyoclear/tsgbuilder FP analysis** — Analyze dead-code and docs-drift FP rates for matrix refinement

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
