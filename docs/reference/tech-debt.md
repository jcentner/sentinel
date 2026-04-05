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
**Status**: Resolved (Session 5)
**Severity**: Medium
**Introduced**: Phase 1
**Description**: The SQLite store tracks a `SCHEMA_VERSION` integer but has no migration framework. Schema changes require manual SQL scripts or database recreation.
**Impact**: Upgrading between versions may lose data.
**Proposed resolution**: Add a simple migration runner (ordered SQL files or Python functions keyed by version) before Phase 2 adds new tables.
**Resolution**: Implemented migration framework in `store/db.py`. Migrations are ordered `(version, description, sql)` tuples applied sequentially. Base schema (v1) is always created, then pending migrations are applied on DB open. First migration (v2) adds `finding_persistence` table.

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

### TD-006: dep-audit audits current environment, not target repo
**Status**: Resolved (Session 4)
**Severity**: Medium
**Introduced**: Phase 1
**Description**: The dep-audit detector runs `pip-audit` against the running Python environment rather than parsing the target repo's declared dependencies (pyproject.toml, requirements.txt). When scanning an external repo, it reports vulnerabilities in *Sentinel's own* deps rather than the target's.
**Impact**: dep-audit findings are misleading when the target repo is not the current venv. Eval tests exclude dep-audit findings to avoid noise.
**Proposed resolution**: Parse the target repo's dependency manifest and either (a) run `pip-audit -r requirements.txt` pointing at the target, or (b) resolve dependencies in a temporary venv.

### TD-007: Finding timestamp lost on DB round-trip
**Status**: Resolved (Session 4)
**Severity**: Low
**Introduced**: Phase 1
**Description**: `_row_to_finding` in `findings.py` does not restore the `timestamp` column from the database. Findings reloaded from the store get a new `datetime.now()` via the dataclass default.
**Impact**: Historical timing data is silently lost when retrieving findings later.
**Proposed resolution**: Parse the stored `created_at` column into the Finding's `timestamp` field in `_row_to_finding`.

### TD-008: Poetry pyproject.toml dependency format not supported
**Status**: Active
**Severity**: Low
**Introduced**: Phase 2
**Description**: The docs-drift dependency drift check only parses PEP 621 `[project.dependencies]` and pip `requirements.txt`. Poetry's `[tool.poetry.dependencies]` format is not supported.
**Impact**: Repos using Poetry will get no dependency drift detection.
**Proposed resolution**: Add a Poetry-format parser branch in `_check_dependency_drift`.

## Resolved

- **TD-003**: Schema migration system implemented in `store/db.py` with ordered migrations and version tracking.
- **TD-006**: dep-audit now targets the repo's declared dependencies (pyproject.toml or requirements.txt), not the running environment.
- **TD-007**: `_row_to_finding` now restores the `created_at` timestamp from the database.

## Won't Fix

(None yet)
