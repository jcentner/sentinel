# Tech Debt Tracker

Tracked technical debt items. These are known compromises, shortcuts, or deferred improvements. Each item should have a clear description of what's owed and why it matters.

## Format

```

## Active

### TD-002: Sync detector interface
**Status**: Active
**Severity**: Low
**Introduced**: Phase 1
**Description**: Detectors use synchronous `detect()` rather than `async detect()` as originally spec'd. All current detectors call subprocesses synchronously.
**Impact**: Detectors run sequentially. No parallelism.
**Proposed resolution**: Migrate to async in Phase 2 when concurrent detector execution matters. Spec updated to reflect sync for now.

### TD-043: Cross-detector data flow for LLM targeting
**Status**: Active
**Severity**: Medium
**Introduced**: Session 29 (multi-repo validation analysis)
**Description**: git-hotspots identifies high-churn, fix-heavy files but this information isn't available to LLM-assisted detectors (semantic-drift, test-coherence). Each detector runs independently with no shared context. High-churn files are the best candidates for deep LLM analysis, but there's no mechanism to prioritize them.
**Impact**: LLM detectors treat all files equally instead of focusing on the highest-risk files first. Wastes LLM budget on stable files while potentially missing issues in frequently-broken ones.
**Proposed resolution**: Add a pre-scan phase that runs cheap heuristic detectors first and builds a "risk profile" per file. LLM detectors can then consume this profile to prioritize which files to analyze deeply. Could be as simple as a `context.risk_signals` dict populated by git-hotspots and complexity before LLM detectors run.

### TD-047: GitHub config not editable from web UI
**Status**: Active (deliberate — see ADR-015)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The `/github` page shows whether GitHub env vars are configured but provides no way to set them. Token must remain env-var-only for security. Owner/repo could be added to sentinel.toml but the value is low — most users set these once.
**Impact**: Minor setup friction.
**Proposed resolution**: Won't implement token editing (security). May add owner/repo to sentinel.toml in future if demand emerges.

### TD-053: Roadmap phases/ directory is stale and inconsistent
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: `roadmap/phases/` has 5 of ~10 phases with plan files (phases 3, 4, 5, 6b, 8 have no files). All phases are complete. The `phases/README.md` is entirely stale — lists only Phase 0 as complete and says "Upcoming: Phase plans will be added as development progresses." The phase model served its purpose during development but is now dead weight.
**Impact**: Confusing for anyone navigating the roadmap. Creates maintenance overhead. Ironic docs-drift in a docs-drift detection tool.
**Proposed resolution**: Archive phases/ to `roadmap/archive/phases/` or delete. Update roadmap/README.md to note all phases are complete and future work uses a slice-based model tracked in CURRENT-STATE.md.

### TD-055: README length (~400 lines) — delegate detail to wiki/docs
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: README is ~400 lines covering installation, full CLI reference, web UI feature list, scheduling, configuration, architecture overview, and development setup. Most of this is better placed in wiki pages or docs/.
**Impact**: Long READMEs are less scannable. First impressions matter.
**Proposed resolution**: Keep README to ~150 lines: problem statement, quick start (install + first scan + serve), link to wiki for full docs. Move detailed CLI reference, web UI docs, configuration, scheduling, and architecture to wiki pages.

### TD-045: Ground truth too small for statistical confidence
**Status**: Active
**Severity**: Low
**Introduced**: Session 29 (multi-repo validation analysis)
**Description**: The eval fixture has 30 seeded TPs across 8 detectors. Multi-repo validation covered 4 repos but most detectors had <50 annotated findings. Not enough for meaningful precision confidence intervals.
**Impact**: Cannot make statistically rigorous accuracy claims. Regression gate (P≥70%, R≥90%) is effective for catching regressions but doesn't validate real-world accuracy.
**Proposed resolution**: Post-PyPI: build annotated ground truth on 5-10 diverse repos with ≥50 labeled findings per detector. Track precision/recall per detector, not just aggregate.

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

### TD-016: Serial LLM judge bottleneck
**Status**: Active
**Severity**: Medium
**Introduced**: Phase 1 (supersedes aspect of TD-002)
**Description**: The judge calls `provider.generate()` sequentially for each finding at ~4s/call. 50 findings = 3.3 min, 100 = 7 min. Combined with synthesis (~40s for 10 clusters), total LLM wall time is 7+ min for moderate repos.
**Impact**: Morning report latency scales linearly with finding count. Tolerable for small repos but a bottleneck for repos with 50+ findings.
**Proposed resolution**: Near-term: batch 3-5 findings per judge prompt to cut per-call overhead. Medium-term: async/concurrent judge calls (related to TD-002). Long-term: skip judge for high-confidence deterministic findings (confidence ≥ 0.95).

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
**Description**: Finding cluster synthesis requires `model_capability >= standard`. Since the default model is Qwen3.5 4B (`basic` tier), synthesis is disabled for most users. The noise-reduction step that collapses N symptoms into 1 root cause simply doesn't run in the default configuration.
**Impact**: Default users get noisier reports than the system is capable of producing. Pattern-based clustering in report.py partially compensates but lacks root-cause annotation.
**Proposed resolution**: Consider a simplified synthesis prompt ("are these the same issue?" → yes/no) that could work at `basic` tier. Reserve full root-cause analysis for `standard+`.

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

