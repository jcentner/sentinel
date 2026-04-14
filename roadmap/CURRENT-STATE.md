# Current State — Sentinel

> Last updated: Session 48 — Phase 15 ICD v2 cloud benchmarks complete

**Phase Status**: In Progress

## Latest Session Summary

### Current Objective
Phase 15: Intent-comparison v2 — post-LLM filtering + calibration. Goal: <25% FP rate.

### What Was Accomplished

#### ICD v2 Implementation (3f5654b)
- Rewrote `_filter_contradictions()` with 3-layer post-LLM filter: structural validity, specificity (min 30 chars, vague phrase detection), evidence quotes
- Improved prompt with FP examples and required `quote_a`/`quote_b` fields
- Dynamic confidence scoring based on quote presence
- 8 new filter tests, 64 ICD tests total, 1376 total tests passing

#### is_test_file fix (f8e6a72)
- Fixed `is_test_file()` to use relative paths — repos nested under `tests/` directory had ALL files classified as test files

#### ICD v2 Benchmarks (5ab789a)
- **sample-repo**: Both 4b and 9b achieve **100% ICD precision, 100% ICD recall** (seeded `process_records` TP found)
- **sentinel self-scan**: 4b=15 findings (50 calls, 67s), 9b=6 findings (50 calls, 233s)
- **pip-tools**: 4b=3 findings (21 calls, 32s), 9b=2 findings (21 calls, 53s)
- **v1→v2 reduction on pip-tools**: 85-94% fewer findings (20→3 / 31→2)
- Full-suite sample-repo: 4b=36 findings (92%P, 92%R), 9b=38 findings (92%P, 97%R)

#### Prior: Ollama full-suite benchmarks (02646a7)
- qwen3.5:4b on sample-repo: 94% precision, 91% recall, 14.8s
- qwen3.5:9b on sample-repo: 94% precision, 97% recall, 36.1s
- qwen3.5:4b self-scan: 398 findings incl. 5 ICD, 150s
- Local models achieve 80-83% LLM precision vs cloud 85-100%

### Key Commits This Session
- `02646a7` bench(models): expand Ollama benchmarks for full detector suite
- `0eaa69d` test(icd): seed sample-repo with ICD ground truth
- `3f5654b` feat(intent-comparison): ICD v2 with post-LLM filtering
- `f8e6a72` fix(intent-comparison): use relative path for is_test_file check
- `5ab789a` bench(icd-v2): add ICD v2 benchmarks across 3 repos x 2 local models
- `e526551` fix(lint): resolve ruff SIM102 and RUF012 in ICD v2 code
- `a4eae86` docs(icd-v2): fix stale references post-ICD v2 redesign

#### Session 48
- `002a2da` fix(test): update JS ICD test mock to match v2 schema (CI fix)
- `784c1fa` fix(hooks): add pytest to slice-gate stop hook
- `b635e8b` bench(icd-v2): Azure cloud model benchmarks across 3 repos x 3 models

### Repository State
- **Tests**: 1419 passing
- **CLI commands**: 21
- **Web routes**: 21
- **VISION-LOCK**: v7.0 (Phase 15 added)

### What Remains / Next Priority
1. ~~Run ICD v2 with cloud models~~ **DONE** — nano=Fair, mini=Good, gpt-5.4=Excellent
2. **Expand sample-repo ICD ground truth** — 1 TP is not statistically significant for confident ratings
3. **Manual review of sentinel ICD findings** to estimate TP rate without ground truth (nano=47, mini=30, gpt-5.4=15)
4. **Consider re-enabling ICD by default** once ground truth expanded
5. **Vision expansion**: Proceed with remaining directions (2-5) after ICD v2 is fully validated

### Decisions Made
- ICD v2 post-LLM filter thresholds: `_MIN_REASON_CHARS=30`, `_VAGUE_PHRASES` set, quote-based confidence
- Used `relative_to(repo_root)` for is_test_file check (was absolute path causing false test classification)

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
