# Tech Debt Tracker

Tracked technical debt items. These are known compromises, shortcuts, or deferred improvements. Each item should have a clear description of what's owed and why it matters.

## Format

```

## Active

### TD-002: Sync detector interface
**Status**: Partially resolved (ADR-017, Session 43)
**Severity**: Low
**Introduced**: Phase 1
**Description**: Detectors use synchronous `detect()` rather than `async detect()` as originally spec'd. All current detectors call subprocesses synchronously.
**Impact**: Phase 1 (heuristic) detectors now run in parallel via thread pool. Phase 2 (LLM-assisted) detectors still run sequentially — each makes multiple internal LLM calls that are now individually faster via async providers.
**Proposed resolution**: Adding an optional `async_detect()` to the Detector protocol for LLM detectors to use `agenerate()` internally. Lower priority since the judge/synthesis async (ADR-017) addressed the main bottleneck.

### TD-047: GitHub config not editable from web UI
**Status**: Active (deliberate — see ADR-015)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The `/github` page shows whether GitHub env vars are configured but provides no way to set them. Token must remain env-var-only for security. Owner/repo could be added to sentinel.toml but the value is low — most users set these once.
**Impact**: Minor setup friction.
**Proposed resolution**: Won't implement token editing (security). May add owner/repo to sentinel.toml in future if demand emerges.

### TD-009: VR-002 built-in scheduling not implemented
**Status**: Active
**Severity**: Low
**Introduced**: Session 12
**Description**: VISION-REVISION-002 specified built-in scheduling within `sentinel serve` (cron expression or interval via `sentinel.toml`). This was deliberately not implemented. The architecture overview, prior session decisions, and codebase consistently treat Sentinel as a single-run tool triggered externally by cron or systemd timers.
**Impact**: Users who expected `sentinel serve` to also handle scheduling must configure system cron/systemd instead. This is well-documented in the README scheduling section.
**Proposed resolution**: Won't implement unless a compelling use case emerges. System schedulers are more reliable, observable, and configurable than an application-level scheduler. See VISION-REVISION-004 for rationale.

### TD-011: Most detectors duplicate existing dev tooling
**Status**: Active
**Severity**: Low
**Introduced**: Session 19 (identified via critical analysis)
**Description**: Lint-runner, eslint-runner, go-linter, rust-clippy, and todo-scanner largely duplicate what standard dev toolchains (CI linting, editor linting) already provide. They add value only for repos that don't already run these tools.
**Impact**: Sentinel's findings are mostly things developers already know about, limiting the product's perceived value. Success criterion #10 ("surface issues the dev didn't already know about") is only partially met because of this.
**Proposed resolution**: Accepted as-is — these detectors are cheap to maintain and useful for repos without CI linting. New development investment should focus on cross-artifact semantic detectors (Phase 5) that provide analysis nothing else does. No need to remove existing detectors.

### TD-024: `--json-output` error envelope inconsistency
**Status**: Active
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Description**: JSON output shapes differ by command and by success/failure. Some error paths write to stderr with no JSON (e.g., `create-issues` with no config). Exit codes conflate "below target" with "errored" (eval uses exit 1 for both). No consistent envelope like `{"ok": true, "data": ...}`.
**Impact**: Agents must special-case each command's output format. Reduces reliability of automated Sentinel consumption.
**Proposed resolution**: Define and document a standard JSON envelope for all `--json-output` commands. Use distinct exit codes for "ran but below threshold" (e.g., exit 2) vs. "command errored" (exit 1).

### TD-032: Synthesis gated to standard+ tier, off by default
**Status**: Active
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Description**: Finding cluster synthesis requires `model_capability >= standard`. Since the default model is Qwen3.5 4B (`basic` tier), synthesis is disabled for most users. The noise-reduction step that collapses N symptoms into 1 root cause simply doesn't run in the default configuration. With ADR-016 (benchmark-driven quality), the gating should also consider benchmark data — if a model benchmarks well, it should qualify for synthesis regardless of tier label.
**Impact**: Default users get noisier reports than the system is capable of producing. Pattern-based clustering in report.py partially compensates but lacks root-cause annotation.
**Proposed resolution**: Consider a simplified synthesis prompt ("are these the same issue?" → yes/no) that could work at `basic` tier. Also consider gating on benchmark quality rather than tier alone.

### TD-039: Doc data duplication (hardcoded counts)
**Status**: Active
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review, H9)
**Description**: Test count (1013), detector count (14), and schema version are hardcoded in 2-4 files each (README, VISION-LOCK, CURRENT-STATE, overview.md). Changes require manual multi-file updates.
**Impact**: Counts go stale silently. Already caught overview.md citing "SQLite v7" when actual schema is v10 (fixed in Session 26).
**Proposed resolution**: Accept for now. Building a single-source mechanism is over-engineered for the current project size. Mitigated by the reviewer subagent's post-implementation consistency checks and the doc-sync checklist in the autonomous builder workflow.

### TD-041: Docs-drift treats example text as file path references
**Status**: Partially resolved (Session 28)
**Severity**: Low (reduced from Medium)
**Introduced**: Session 27 (pip-tools real-world validation)
**Resolution**: Added `_is_example_context()` helper that checks for "e.g.", "for example", "such as", "like" phrases in the 30-char window before backtick-wrapped paths. Eliminated 1/3 pip-tools FPs (the "e.g. `release/v3.4.0`" case). Two edge cases remain: feature descriptions in CHANGELOG and example filenames without explicit example-context phrases.

### TD-057: intent-comparison detector produces >90% false positives
**Status**: Active
**Severity**: High
**Introduced**: Session 45 (benchmark audit)
**Description**: The intent-comparison detector has fundamental design issues that make it unreliable:
1. Runs even with `model_capability=basic` despite declaring `advanced` requirement (warning-only gate in `runner.py`)
2. No post-LLM filtering — every LLM-reported contradiction becomes a finding regardless of confidence or plausibility
3. Prompt lacks concrete false-positive examples to calibrate the model
4. Hardcoded confidence thresholds (0.55 basic, 0.70 enhanced) with no validation
5. 50-call budget (`_MAX_PER_SCAN`) with no quality check or early stop
Results: 0 findings on sample-repo (too few 3-artifact symbols), 35 findings on pip-tools (all likely FP). Rated POOR (>90% estimated FP) for cloud-small.
**Impact**: Users who enable this detector get a flood of false positives, damaging trust in the system. The detector is the noisiest component by a large margin.
**Proposed resolution**: Redesign needed — add hard capability gate (skip if model < advanced), add post-LLM filtering (reject low-confidence or vague contradictions), add concrete FP examples to prompt, test on multiple repos before re-rating. Consider disabling by default until redesign is complete.

### TD-058: Benchmark precision conflates deterministic and LLM detectors
**Status**: Active
**Severity**: Medium
**Introduced**: Session 45 (benchmark audit)
**Description**: `sentinel benchmark` reports a single headline precision/recall that combines all 18 detectors. On sample-repo, 27 of 36–40 findings (varies by model) come from deterministic detectors that are identical regardless of model. This makes the headline numbers misleading for model comparison — "92% precision (mini)" vs "85% precision (nano)" is mostly about 2-3 extra LLM-detector findings, not meaningful quality difference.
**Impact**: Published compatibility matrix entries may overstate or understate model quality. Users comparing models can't tell what's signal vs noise.
**Proposed resolution**: Add per-category precision (deterministic vs LLM-assisted) to benchmark output. Report LLM-detector precision separately so model comparisons are meaningful. The `benchmark.toml` files already capture per-detector counts — the aggregation logic needs refinement.

