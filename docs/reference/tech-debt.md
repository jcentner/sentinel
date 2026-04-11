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

### TD-046: Settings page is read-only — no sentinel.toml creation or editing
**Status**: Active
**Severity**: Medium
**Introduced**: Session 34 (user feedback)
**Description**: The `/settings` page displays current config but cannot edit it. If no `sentinel.toml` exists, it shows "No sentinel.toml found" with no way to create one. Users must manually edit config files. The vision lock specifies "Dual interface: feature parity between CLI and web UI" but the web UI has no config editing capability equivalent to `sentinel init` or manual TOML editing.
**Impact**: Web UI is not a first-class interaction method for configuration. Users who prefer the browser must still use the CLI or a text editor for all config changes.
**Proposed resolution**: Add a config editor to the settings page: create `sentinel.toml` if missing (equivalent to `sentinel init`), edit key fields (model, provider, enabled/disabled detectors, capability tier), and save. Consider making the Detectors/Compatibility page the primary configuration surface for detector + model selection.

### TD-047: GitHub config not editable from web UI
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The `/github` page shows whether GitHub env vars are configured but provides no way to set them. Users must set `SENTINEL_GITHUB_OWNER`, `SENTINEL_GITHUB_REPO`, `SENTINEL_GITHUB_TOKEN` outside the UI.
**Impact**: Setup friction for users who want to use the GitHub integration from the browser flow.
**Proposed resolution**: Add a config form to the GitHub page. Could set env vars for the running process or persist to `sentinel.toml` (owner/repo only — token should remain env-var-only for security).

### TD-048: Scan form "LLM Model" label is ambiguous
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The scan page labels the model field "LLM Model" but this sets the model for the judge and all LLM-assisted detectors. The label implies it's only for one purpose. No embedding model selector is provided with comparable UX.
**Impact**: User confusion about what the model field controls. Embedding model selection is less discoverable.
**Proposed resolution**: Rename to "Model" or "LLM / Judge Model" with a help tooltip explaining scope. Add embedding model to a comparable dropdown or autocomplete.

### TD-049: Compatibility page shows redundant deterministic detector info
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The deterministic detectors section lists every non-LLM detector with "No — detection is model-free." This information is implied by the section title and doesn't help the user make decisions. The page's value is helping users choose models for LLM detectors.
**Impact**: Visual noise. The page is longer than necessary without adding decision-relevant information.
**Proposed resolution**: Either remove the deterministic section entirely, or collapse it to a single sentence: "All other detectors are deterministic and model-free." Alternatively, show language-specific detectors with flags indicating whether they apply to the currently-opened repo (if repo context is available).

### TD-050: Model Classes table tok/s data not useful without per-user hardware context
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The Model Classes table at the bottom of `/compatibility` shows static tok/s estimates. Performance varies enormously by hardware, making static numbers misleading. Would be more valuable if populated dynamically from actual scan data.
**Impact**: Users may set expectations based on irrelevant speed numbers.
**Proposed resolution**: Remove static tok/s or mark as "approximate, varies by hardware." Better: populate Model Classes dynamically from actual scan timing data for the user's repo (if scan history exists). Show real measured tok/s from their runs.

### TD-051: Compatibility matrix model list outdated (Sonnet 4 → 4.6)
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The compatibility matrix lists "Claude Sonnet 4" as a cloud-frontier model. Sonnet 4.6 is the current frontier model, on par with GPT-5.4. The matrix should reflect current model landscape.
**Impact**: Stale model references reduce trust in the matrix data.
**Proposed resolution**: Update cloud-frontier examples to Sonnet 4.6: "GPT-5.4, Claude Sonnet 4.6" in compatibility.py and all references.

### TD-052: Compatibility page naming — consider "Detectors" 
**Status**: Active
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: The page is named "Compatibility" but shows all detector information (LLM-assisted matrix, deterministic list, model classes). "Detectors" may be a better name since the page is becoming a detector reference + configuration surface.
**Impact**: Navigation clarity. Minor.
**Proposed resolution**: Rename to "Detectors" if the page evolves to include detector toggles and per-detector model selection (see TD-046). Keep "Compatibility" if it remains read-only reference.

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

