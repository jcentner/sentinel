# Current State — Sentinel

> Last updated: Session 26 — Systemic review audit + gap fixes

## Latest Session Summary

### Current Objective
Audit all 36 findings from the systemic review executive report (C1-C2, H1-H14, M1-M20) to verify fixes and close remaining gaps.

### What Was Accomplished

#### Systemic Review Double-Check
Cross-referenced every finding from the executive report against actual implementations. Two verification passes: 14 code-level checks + 8 doc/status checks.

**Results**: 29/36 properly fixed, 5 accepted trade-offs, 4 gaps found and addressed:

| Gap | Finding | Fix Applied |
|-----|---------|-------------|
| M17 | CURRENT-STATE.md bloated to 1642 lines | Trimmed to ~100 lines, archived Sessions 1-24 with git pointer |
| M14 | `sentinel doctor` doesn't validate config | Added `sentinel.toml` validation check to doctor command |
| M18 | No contributor reading guide | Added "Codebase Reading Guide" section to CONTRIBUTING.md |
| M19 | eval/benchmark shared `evaluate()` undocumented | Added "Benchmark vs Eval" comparison table to benchmarking.md |

**Additional fixes found during audit:**
- Fixed stale "SQLite v7" → "SQLite v10" in `docs/architecture/overview.md` (H9 staleness)
- Tracked H9 (doc data duplication) as TD-039 — accepted trade-off with consistency checks as mitigation

#### Items requiring human decision (not resolved autonomously)
- **H1 / OQ-014**: No ground truth for LLM-assisted detectors (semantic-drift, test-coherence). Strategy for real-world corpus needs human input.
- **H9 / TD-039**: Hardcoded counts duplicated across 2-4 files. Single-source mechanism is over-engineered; accepted with reviewer checks.

### Verification
- **Tests**: 1013 passed, 3 skipped
- **Ruff**: All checks passed
- **No regressions**: Full test suite clean

### Repository State
- **Tests**: 1013 passing
- **VISION-LOCK**: v4.6
- **Tech debt items**: 39 total, 32 resolved, 7 remaining (6 accepted/low + 1 medium)
- **Open questions**: 16 total, 13 resolved, 3 remaining (OQ-006, OQ-014, OQ-016)
- **ADRs**: 14
- **Schema version**: 10
- **Detectors**: 14

### Files Modified This Session
- `roadmap/CURRENT-STATE.md` — trimmed 1642→~100 lines (M17), updated for Session 26
- `src/sentinel/cli.py` — doctor command validates sentinel.toml (M14)
- `CONTRIBUTING.md` — added Codebase Reading Guide section (M18)
- `docs/reference/benchmarking.md` — added Benchmark vs Eval comparison (M19)
- `docs/architecture/overview.md` — fixed stale SQLite v7→v10 (H9)
- `docs/reference/tech-debt.md` — added TD-039 (H9 tracking)

### What Remains / Next Priority

#### Remaining Active Tech Debt (7 items)
- **TD-002** (Low): Sync detector interface — accepted, no parallelism needed yet
- **TD-009** (Low): VR-002 scheduling — won't implement, use system cron
- **TD-011** (Low): Detectors duplicate dev tooling — accepted trade-off
- **TD-016** (Medium): Serial LLM judge bottleneck — optimization, not blocking
- **TD-024** (Low): JSON error envelope inconsistency — cosmetic
- **TD-032** (Low): Synthesis gated to standard+ — by design
- **TD-039** (Low): Doc data duplication — accepted, mitigated by consistency checks

#### Remaining Open Questions (3 items)
- **OQ-006** (Low): SQL anti-pattern detector design — deferred
- **OQ-014** (Medium): Real-world ground truth corpus — needs human input
- **OQ-016** (Low): generate() protocol evolution — not urgent

#### Recommended Next Work (priority order)
1. **Stale samples**: samples/ directory has report and JSON from Session 8; regenerate
2. **PyPI publication**: Release workflow exists, needs `pypi` environment in GitHub settings, tag v0.1.0
3. **OQ-014 resolution**: Requires human decision on ground truth corpus strategy
4. **CI full-pipeline eval**: Add `--full-pipeline --replay-file` step to CI once recordings are captured with a real model
5. **Model comparison benchmarks**: Run benchmarks with different models to quantify quality differences
6. **TD-016 optimization**: Batch judge prompts (only if scan times become a user complaint)

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
