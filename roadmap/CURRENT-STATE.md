# Current State — Sentinel

> Last updated: 2026-04-04 (Session 4)

## Session 4 Summary

### Current Objective
Fix code review findings, validate with real Ollama, and rigorously audit detector precision/recall.

### What Was Accomplished

**Turn 1 — Code review fixes (14 findings):**
1. Created shared `src/sentinel/core/ollama.py` (check_ollama utility)
2. Lazy httpx imports everywhere
3. Format string crash fixes (f-strings instead of .format())
4. `skip_judge` → `skip_llm` config rename in detector context
5. stdlib `tomllib` replacing hand-rolled TOML parsing
6. Generic CLI source finder, dead code cleanup, docs updates

**Turn 2 — Real Ollama testing:**
7. Fixed `think: false` required for qwen3.5 reasoning model
8. Updated default model from `qwen3:4b` to `qwen3.5:4b`
9. Fixed judge `_build_prompt` .format() crash (brace escaping)
10. Full end-to-end scan validated: 4 detectors + LLM judge producing quality reports

**Turn 3 — Deep precision/recall audit:**
11. Deep audit subagent found 4 critical bugs, 9 FP/FN risks, 15 test gaps
12. Created seeded test repo at `tests/fixtures/sample-repo/` with ground truth
13. Measured baseline: 58% precision, 85% recall (7 FP, 2 FN)
14. Applied 7 fixes:
    - Fenced code block state tracking in `_check_stale_references`
    - `finditer` for multi-TODO per line + non-greedy regex with lookahead
    - Nearest (last) comment marker for proximity check
    - Inline path dual resolution (doc-dir + repo-root)
    - Indented fenced code block regex (up to 3 spaces)
    - Stale model fallback string
    - Report evidence multi-line indentation
15. Post-fix: 100% precision, 100% recall (13 TP, 0 FP, 0 FN)

**Turn 4 — Eval test + commit:**
16. Created `tests/test_eval.py` — 7 tests validating precision/recall against ground truth
17. Added TD-006, TD-007, TD-008 to tech-debt tracker
18. 177 tests pass, lint clean
19. Committed: `fix(detectors): 7 precision/recall fixes + eval test with ground truth`

### Repository State
- **Phase 0 (Foundation)**: Complete
- **Phase 1 (MVP Core)**: Complete
- **Phase 2 (Docs-Drift)**: Complete
- **Phase 3 (Refinement)**: Significantly advanced — precision/recall at 100% on ground truth
- **Implementation code**: 14 Python modules in `src/sentinel/`
- **Test code**: 13 test files, 177 tests (including 7 eval tests)
- **Detectors**: todo-scanner, lint-runner, dep-audit, docs-drift
- **Vision lock**: Baselined (Session 1), one revision
- **Open questions**: 4 open (OQ-002, OQ-004, OQ-005, OQ-006), 3 resolved
- **ADRs**: 8 accepted
- **Tech debt**: 8 items (TD-001 through TD-008)
- **Lint**: Clean (ruff)

### Test Results
```
177 passed in 3.42s
ruff check: All checks passed
Eval: 100% precision, 100% recall on seeded ground truth
```

### Decisions Made This Session
1. `think: false` required in all Ollama API calls for reasoning models
2. Default model `qwen3.5:4b` (was `qwen3:4b`)
3. Seeded test repo as formal evaluation mechanism (ADR-008 criteria)
4. dep-audit excluded from eval tests (audits wrong env — TD-006)
5. Code block state machine for fenced block tracking (not regex-only)
6. Dual path resolution for inline paths (doc-dir + repo-root)
7. Non-greedy TODO regex with lookahead for multi-match support

### What Remains / Next Priority
**Phase 3 continued / Phase 4 planning:**
1. Finding persistence scoring (recurring findings gain confidence) — deferred
2. Incremental run optimization (only scan changed files) — deferred
3. Consider git-hotspots detector (Phase 4)
4. Consider Semgrep integration (Phase 4)
5. GitHub issue creation workflow (Phase 5)
6. Address TD-006 (dep-audit wrong env) — medium priority
7. Address TD-007 (timestamp round-trip) — low priority
8. Address TD-008 (Poetry format) — low priority

### Blocked Items
- pip-audit not installed in venv (dep-audit detector skipped during self-scan)
  - Not blocking: `pip install pip-audit` resolves it

### Files Created This Session
- `src/sentinel/core/ollama.py` — shared Ollama utility
- `tests/fixtures/sample-repo/` — seeded test repo (7 files)
- `tests/fixtures/SAMPLE-REPO-GROUND-TRUTH.md` — ground truth manifest
- `tests/test_eval.py` — precision/recall eval test (7 tests)

### Files Modified This Session
- `src/sentinel/detectors/docs_drift.py` — 7 fixes (code blocks, dual resolution, indented fences, model fallback)
- `src/sentinel/detectors/todo_scanner.py` — 3 fixes (finditer, non-greedy regex, nearest marker)
- `src/sentinel/core/report.py` — evidence per-line indentation
- `src/sentinel/core/judge.py` — f-strings, think:false, shared check_ollama
- `src/sentinel/core/runner.py` — default model, skip_llm config
- `src/sentinel/config.py` — default model
- `pyproject.toml` — ruff exclude for fixtures
- `docs/reference/tech-debt.md` — TD-006, TD-007, TD-008

## Session 3 Summary (Previous)
- Phase 2 (Docs-Drift) complete: stale refs, dep drift, LLM doc-code comparison
- Phase 3 refinements: TODO FP reduction, report fingerprint IDs
- 170 tests, lint clean

## Session 2 Summary (Previous)
- Implemented all 15 Phase 1 MVP slices
- 126 tests, ruff clean
- Full pipeline: 3 detectors → fingerprint → dedup → context → judge → report

## Session 1 Summary (Previous)
- Created VISION-LOCK.md, CURRENT-STATE.md, agent-improvement-log.md
- Created ADR-008, resolved OQ-007
- Created Phase 1 plan with 15 slices
- Phase 0 complete
