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

### TD-001: Context gatherer uses file-proximity only
**Status**: Active
**Severity**: Medium
**Introduced**: Phase 1
**Description**: The context gatherer uses simple file-proximity heuristics (±5 lines, naming-convention test file matching, git log) instead of embedding-based retrieval.
**Impact**: Lower-quality context for LLM judge, reducing judgment accuracy.
**Proposed resolution**: Add embeddings via Qwen3-Embedding-0.6B + SQLite-vec in Phase 2 (see OQ-004).

### TD-002: Sync detector interface
**Status**: Active
**Severity**: Low
**Introduced**: Phase 1
**Description**: Detectors use synchronous `detect()` rather than `async detect()` as originally spec'd. All current detectors call subprocesses synchronously.
**Impact**: Detectors run sequentially. No parallelism.
**Proposed resolution**: Migrate to async in Phase 2 when concurrent detector execution matters. Spec updated to reflect sync for now.

### TD-003: No schema migration system
**Status**: Active
**Severity**: Medium
**Introduced**: Phase 1
**Description**: The SQLite store tracks a `SCHEMA_VERSION` integer but has no migration framework. Schema changes require manual SQL scripts or database recreation.
**Impact**: Upgrading between versions may lose data.
**Proposed resolution**: Add a simple migration runner (ordered SQL files or Python functions keyed by version) before Phase 2 adds new tables.

### TD-004: Config values not type-validated
**Status**: Active
**Severity**: Low
**Introduced**: Phase 1
**Description**: `load_config()` reads `sentinel.toml` values but does not validate types. `skip_judge = "yes"` or `model = 42` would be silently accepted.
**Impact**: Confusing runtime errors from bad config instead of clear validation messages.
**Proposed resolution**: Add type checks at config load time or use a validation library.

### TD-005: TODO comments in markdown are invisible
**Status**: Active
**Severity**: Low
**Introduced**: Phase 2
**Description**: The TODO scanner skips `.md` files (to avoid false positives from docs-drift's domain), and the docs-drift detector doesn't scan for TODO/FIXME comments in markdown. HTML comment TODOs (`<!-- TODO: ... -->`) in markdown are invisible to both detectors.
**Impact**: TODO comments in markdown documentation are never surfaced.
**Proposed resolution**: Either add a markdown-aware TODO pattern to the TODO scanner (only matching HTML comments) or add a simple TODO check to the docs-drift detector.

## Resolved

(None yet)

## Won't Fix

(None yet)
