# Current State — Sentinel

> Last updated: Session 49 — ICD precision measured, detector fixes applied

**Phase Status**: Blocked: Phase 15 ICD precision is Poor across all models (best: gpt-5.4 at 43% precision on real repos). The detector finds real bugs but noise dominates. Awaiting human decision on whether to close phase and accept measured ratings, or iterate further on FP reduction.

## Latest Session Summary

### Current Objective
Phase 15: Intent-comparison v2 — post-LLM filtering + calibration. Goal: <25% FP rate.

### What Was Accomplished

#### Measured ICD Precision (empirical TP/FP annotation)
Ran ICD on pip-tools + sentinel self-scan with 3 Azure models, manually verified every gpt-5.4 finding and all mini findings:

| Model | Real-repo findings | TP | Precision | FP Rate |
|-------|-------------------|-----|-----------|---------|
| gpt-5.4-nano | 59 | 1 | ~2% | ~98% |
| gpt-5.4-mini | 24 | 1 | 4% | ~96% |
| gpt-5.4 | 7 | 3 | 43% | ~57% |

#### Root cause: cross-class test contamination
`_build_test_lookup` keyed by function name only — `test_check_health` tests from TestOllamaProvider, TestOpenAICompatibleProvider, and TestAzureProvider ALL got sent to the LLM for any `check_health` function.

#### ICD detector fixes (3 commits)
1. **Class-aware test matching** (48741cf): `_build_test_lookup` returns class_name metadata, `_find_tests_for_symbol` uses class affinity
2. **Remove cross-class fallback** (51499a5): When impl_class is known but no matching tests exist, return empty instead of wrong-class tests
3. **3 FP reduction filters** (c051822): Self-negating gate (drops findings where LLM says "no contradiction"), fixture exclusion (skip tests/fixtures/), archive doc exclusion

#### Real docstring bugs fixed (found by ICD)
- `openai_compat.check_health`: docstring claimed completions+GET fallback, code only does GET
- `ollama.embed_texts`: docstring omitted empty-input shortcut behavior
- `runner.prepare_incremental`: docstring missed HEAD-unchanged case

#### Updated compatibility matrix with measured data (e857be0)
All cloud models rated Poor (measured FP >40%). 4b/9b local marked Untested (pre-fix benchmarks stale).

### Key Commits This Session (Session 49)
- `48741cf` fix(icd): class-aware test matching to reduce cross-class FPs
- `51499a5` fix(icd): remove cross-class fallback, fix 2 TP docstring bugs
- `c051822` fix(icd): add 3 FP reduction filters to post-LLM pipeline
- `e857be0` docs(icd): update compatibility matrix with measured precision data
- `f17b4e9` bench(icd): v2+fixes benchmark results and ground truth annotations

### Repository State
- **Tests**: 1422 passing
- **CLI commands**: 21
- **Web routes**: 21
- **VISION-LOCK**: v7.0 (Phase 15)

### What Remains / Next Priority
1. **Human decision**: Close Phase 15 with honest Poor ratings, or invest more in FP reduction?
2. **ICD FP ceiling**: Dominant pattern is LLM hallucination of evidence — not fixable by better filtering. Needs either self-verification prompting, second-pass validation, or restricting to high-confidence-only findings.
3. **4b/9b re-benchmark**: Local model benchmarks are stale (pre-class-aware-matching). Need to re-run on Ollama machine.
4. **Vision expansion**: Remaining directions (2-5) after Phase 15 is resolved.

### Decisions Made
- ICD's main FP source is LLM hallucination, not bad filtering — the v2 filter catches structural noise but can't catch factually plausible fabrications
- Class-aware test matching helps for class-organized test suites but most FPs come from incorrect LLM analysis, not wrong test matching
- Self-negating gate catches ~30-40% of mini FPs (findings where LLM's own reasoning says "no contradiction")
- gpt-5.4 is the only model with actionable ICD precision (43%) — total findings are low enough (7) for quick human review

### Dominant FP Patterns (from TP/FP annotation)
1. **Hallucinated test assertions**: LLM fabricates tests that don't exist (e.g. claims `test_get_dependencies` asserts `== []`)
2. **Partial class reading**: LLM only sees first part of class, misses embed() method, flags docstring as wrong
3. **Parameter name confusion**: Confuses `num_ctx` with `max_tokens`
4. **Irrelevant doc citations**: Treats benchmark tables, changelogs, glossary entries as behavioral specs
5. **Self-negating findings**: LLM concludes "no contradiction" in its own reason but emits finding anyway (fixed by gate)
6. **Fixture confusion**: Confuses intentionally drifted test fixtures with real tests (fixed by exclusion)

## Vision Expansion Proposal

All goals in VISION-LOCK v6 "Where We're Going" are implemented. Here's what the project has accomplished and where it could go next.

### What Was Accomplished (v5-v6)
- **Async pipeline** (Phase 11): 4.5x speedup via concurrent judge/synthesis, parallel detector execution
- **Multi-language** (Phase 12): Tree-sitter integration for JS/TS, all 4 LLM detectors cross-language
- **Benchmark system** (Phase 13): 3 ground truth repos, per-model×detector quality ratings, per-category eval
- **CLI/Web parity** (Phase 14): 21 CLI commands, 21 web routes, bulk ops, benchmark page, JSON standardization

### What Was Learned
1. **Cross-artifact analysis is the differentiator** — lint/todo detectors overlap with existing tools; docs-drift, test-coherence, and semantic-drift find issues nothing else does
2. **Intent-comparison's >90% FP rate** shows that multi-artifact triangulation needs carefully calibrated prompts and post-LLM filtering, not just more artifacts
3. **Benchmark data drives trust** — switching from assumed tiers to empirical ratings changed how we think about model-detector quality
4. **Small model quality is a ceiling** — 4B models cap at FAIR for LLM detectors; cloud-nano is the quality step-change
5. **Web UI as first-class surface** unlocked triage workflows that CLI alone can't support

### Proposed Next Directions

**Direction 1: Intent-comparison v2 — post-LLM filtering + calibration** ✅ IMPLEMENTED (Phase 15)

**Direction 2: Incremental scanning performance**
Currently scans the full repo even in incremental mode (detectors receive changed_files but still walk the tree). For large repos (10K+ files), startup cost is dominated by file discovery and embedding index building. Implement lazy file discovery, cached AST parsing, and smarter context gathering that only reads changed neighborhoods.

**Direction 3: Scheduled scan + notification**
While Sentinel itself doesn't schedule, the morning report workflow is the core UX. Add a lightweight `sentinel watch` daemon that triggers periodic scans and saves reports. Integrate with OS notifications (desktop, email, Slack webhook) for "new findings since last scan" alerts.

**Direction 4: Finding clustering and trend analysis**
Findings accumulate across runs but there's no cross-run analysis. Add finding clustering (group related findings), trend detection (worsening code areas), and a web dashboard showing health trajectory per directory/module over time.

**Direction 5: Go/Rust LLM detectors**
Tree-sitter already supports Go and Rust, but only JS/TS extractors were built. Extend the extractors module to support Go and Rust function/docstring extraction, enabling all 4 LLM detectors for those languages.

## Previous Sessions (Archived)

To view historical checkpoints: `git log --oneline -- roadmap/CURRENT-STATE.md`
