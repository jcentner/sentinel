# Tech Debt Tracker

Tracked technical debt items. These are known compromises, shortcuts, or deferred improvements. Each item should have a clear description of what's owed and why it matters.

## Format

```
### TD-NNN: Title
**Status**: Active | Resolved | Won't fix
**Severity**: Low | Medium | High
**Introduced**: Date or phase
**Description**: What the debt is
**Impact**: What happens if we don't address it
**Proposed resolution**: How to fix it
```

## Active

### TD-002: Sync detector interface
**Status**: Active
**Severity**: Low
**Introduced**: Phase 1
**Description**: Detectors use synchronous `detect()` rather than `async detect()` as originally spec'd. All current detectors call subprocesses synchronously.
**Impact**: Detectors run sequentially. No parallelism.
**Proposed resolution**: Migrate to async in Phase 2 when concurrent detector execution matters. Spec updated to reflect sync for now.

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

### TD-012: git-hotspots provides statistics without insight
**Status**: Resolved (Session 21)
**Severity**: Low
**Introduced**: Session 19 (identified via critical analysis)
**Description**: The git-hotspots detector correctly identifies high-churn files but doesn't explain *why* the churn matters. A file changed 50 times could be healthy (frequently improved) or problematic (constantly breaking). Without context about *what* changed, churn alone is weak signal.
**Impact**: Findings are technically accurate but not actionable. Developers see "this file changed a lot" and shrug.
**Resolution**: Enriched with commit message classification (fix/refactor/feature/other), author concentration analysis (bus-factor, coordination overhead), and actionable insights in descriptions. Bug-fix-heavy churn escalates severity. Evidence now includes commit type breakdown.

## Resolved

### TD-001: Context gatherer uses file-proximity only
**Status**: Resolved (Session 9)
**Severity**: Medium
**Introduced**: Phase 1
**Resolution**: Embedding-based context gatherer implemented (ADR-009). Opt-in via `embed_model` config. Uses Ollama `/api/embed` endpoint, stores vectors as float32 BLOBs in SQLite (no sqlite-vec needed). Falls back to file-proximity heuristic when embeddings unavailable.

### TD-003: No schema migration system
**Status**: Resolved (Session 5)
**Severity**: Medium
**Introduced**: Phase 1
**Resolution**: Implemented migration framework in `store/db.py`. Migrations are ordered `(version, description, sql)` tuples applied sequentially. Base schema (v1) is always created, then pending migrations are applied on DB open.

### TD-004: Config values not type-validated
**Status**: Resolved (Session 7)
**Severity**: Low
**Introduced**: Phase 1
**Resolution**: `_validate_config()` checks type and key validity at load time. Unknown keys and wrong types raise `ConfigError` with clear messages. 6 tests.

### TD-005: TODO comments in markdown are invisible
**Status**: Resolved (Session 8)
**Severity**: Low
**Introduced**: Phase 2
**Resolution**: Added `_scan_markdown_todos()` to the TODO scanner. Scans `.md`, `.rst`, `.adoc`, `.html` files for `<!-- TODO/FIXME/HACK/XXX: ... -->` HTML comment patterns. 6 new tests.

### TD-006: dep-audit audits current environment, not target repo
**Status**: Resolved (Session 4)
**Severity**: Medium
**Introduced**: Phase 1
**Resolution**: dep-audit now targets the repo's declared dependencies (pyproject.toml or requirements.txt), not the running environment.

### TD-007: Finding timestamp lost on DB round-trip
**Status**: Resolved (Session 4)
**Severity**: Low
**Introduced**: Phase 1
**Resolution**: `_row_to_finding` now restores the `created_at` timestamp from the database.

### TD-008: Poetry pyproject.toml dependency format not supported
**Status**: Resolved (Session 8)
**Severity**: Low
**Introduced**: Phase 2
**Resolution**: `_parse_pyproject_deps()` now reads `[tool.poetry.dependencies]` and `[tool.poetry.group.*.dependencies]`, skipping `python` entries. 4 new tests.

### TD-010: Hardcoded num_ctx in LLM judge
**Status**: Resolved (Session 19)
**Severity**: Low
**Introduced**: Session 18
**Resolution**: `num_ctx` added to `SentinelConfig` (default 2048), threaded through `run_scan` → `judge_findings` → `_judge_single`. Exposed in `sentinel init` scaffold as commented-out option.

## Won't Fix

(None yet)
