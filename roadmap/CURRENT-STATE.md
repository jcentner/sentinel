# Current State — Sentinel

> Last updated: Session 33 — Empirical tier redesign, ADR-011 amendment, per-detector config UI

## Latest Session Summary

### Current Objective
Complete the empirical capability tier redesign and ensure all docs, ADRs, vision, and instructions are consistent with the new tier definitions.

### What Was Accomplished

#### Empirical capability tier redesign (Session 31–33)
- **Tier boundaries are now evidence-based**: 4B and 9B both map to `basic` (same empirical class, scores ~27-32). Cloud-nano (gpt-5.4-nano, ~38-44) is the `standard` boundary. Cloud-small (gpt-5.4-mini ~38-49, Haiku 4.5 ~31-37) maps to `advanced`.
- The tier boundary between basic→standard is the test-coherence quality jump: POOR/FAIR at 4B/9B → GOOD at cloud-nano.
- Added `cloud-small` model class (5 total: 4b-local, 9b-local, cloud-nano, cloud-small, cloud-frontier).

#### ADR-011 amendment
- Amended ADR-011 with empirical tier boundary rationale, benchmark evidence references, cloud-small model class, and updated consequences.

#### Per-detector model overrides in web UI
- Added collapsible "Per-Detector Model Overrides" section to scan form (scan.html).
- Backend parses override arrays into `ProviderOverride` instances with validated fields.
- Detectors can now be individually configured with different models/providers from the UI.

#### `sentinel compatibility` CLI command
- New command: `sentinel compatibility` — prints color-coded terminal matrix.
- Supports `--detector`, `--model`, `--json-output` flags.
- 6 new tests.

#### Compatibility matrix data + docs rewrite
- Updated `src/sentinel/core/compatibility.py` with 5 model classes and dynamic matrix generation.
- Full rewrite of `docs/reference/compatibility-matrix.md` with empirical tier rationale sections.
- Updated `/compatibility` web UI page with tier column and dynamic notes.

#### Vision and instructions alignment
- VISION-LOCK bumped to v4.9 with empirical tier table and rationale paragraph.
- `.github/copilot-instructions.md` updated with empirical tier grounding principle.
- Compatibility-matrix.md sections: "Why 9B local maps to basic, not standard" and "Why cloud-small ≠ cloud-nano".

#### TD-044 dead-code JS/TS FP fix
- Rewrote barrel re-exports, type exports, intra-file refs, package.json entry points. 55 tests.

#### OpenAI provider fix
- `max_completion_tokens` for gpt-5.x with auto-fallback. Added `--api-key-env` CLI flag.

#### Test-coherence prompt refinement
- Explicit "coherent patterns" guidance. Self-scan FPs dropped 14→7 (~50% reduction).

#### LLM detector ground truth + eval fix
- 3 ground truth entries. Eval filters expected entries to only count running detectors.

#### Full-pipeline validation
- Sample-repo: 35 findings, 30 confirmed, 5 rejected. P=97%, R=100%.
- tsgbuilder (Python CLI): 113 raw → 101 dedup → 93 confirmed.
- wyoclear (Next.js): 202 raw → 168 dedup → 152 confirmed, 5 synthesis clusters.

#### Commits this session (Session 31–33)
- `bf74452` — fix(detectors): dead-code JS/TS false positive fixes (TD-044)
- `c9c806d` — feat(benchmark): decouple --skip-judge from --skip-llm
- `0d0547f` — feat(openai): max_completion_tokens for gpt-5.x, --api-key-env
- `b8248f5` — docs(benchmarks): LLM detector validation results and pytest config fix
- `8d8501b` — fix(detectors): test-coherence prompt refinement (14→7 FPs)
- `5d882a8` — feat(eval): LLM detector ground truth, eval active_expected fix
- `66bf98e` — docs(tiers): empirically-grounded capability tiers and model classes
- `798ebe3` — feat(cli): add sentinel compatibility command
- `60fe031` — feat(web): per-detector model overrides in scan form
- `d2805e0` — docs(tiers): amend ADR-011, VISION-LOCK v4.9, empirical tier instructions
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
- **Tests**: 1052 passing, 3 skipped
- **VISION-LOCK**: v4.9
- **PyPI**: `repo-sentinel` v0.1.0 published
- **Tech debt items**: 9 remaining (7 low + 2 medium: TD-016 async judge [deprioritized], TD-043 cross-detector data flow)
- **Open questions**: 18 total, 16 resolved, 2 remaining (OQ-006, OQ-016)
- **ADRs**: 14 (ADR-011 amended with empirical tier rationale)

### What Remains / Next Priority

#### Next priorities
1. **Cross-detector data flow** (TD-043, medium) — Let git-hotspots inform LLM detector targeting
2. **wyoclear/tsgbuilder FP analysis** — Analyze dead-code and docs-drift FP rates for matrix refinement
3. **Real-world benchmark ground truth** — Add ground truth for tsgbuilder/wyoclear to improve eval precision
4. **Cloud-small benchmarking** — Test gpt-5.4-mini and Haiku 4.5 to fill ❓ Untested cells in compatibility matrix

#### Deprioritized
- **Async judge** (TD-016) — Low priority per user; design runs in background so latency is not material

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
