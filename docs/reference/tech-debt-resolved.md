# Tech Debt — Resolved Items

Archived resolved tech debt items. Active items are in [tech-debt.md](tech-debt.md).

## Resolved

### TD-055: README length (~400 lines) — delegate detail to wiki/docs
**Status**: Resolved (Session 38)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Resolution**: Pruned from 404 to 112 lines. Moved CLI reference, web UI feature list, scheduling, custom detectors, config details, and AI agent integration to wiki. Kept: problem statement, what-it-does (compact), quick start, key commands table, minimal config, docs links, dev setup.

### TD-053: Roadmap phases/ directory is stale and inconsistent
**Status**: Resolved (Session 38)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Resolution**: Archived `roadmap/phases/` to `roadmap/archive/phases/`. Updated `roadmap/README.md` to note all phases complete, future work uses slice-based model in CURRENT-STATE.md.

### TD-046: Settings page is read-only — no sentinel.toml creation or editing
**Status**: Resolved (Session 35 — ADR-015)
**Severity**: Medium
**Introduced**: Session 34 (user feedback)
**Resolution**: Settings page rewritten as editable form. Saves to sentinel.toml via new `save_config()` in config.py. Creates file if missing. Groups: Model & Provider, Embeddings, Pipeline, Detectors, Paths. Success toast on save.

### TD-048: Scan form "LLM Model" label is ambiguous
**Status**: Resolved (Session 35)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Resolution**: Renamed to "Model" with hint: "Used by LLM judge and all LLM-assisted detectors."

### TD-049: Compatibility page shows redundant deterministic detector info
**Status**: Resolved (Session 35)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Resolution**: Deterministic detectors section collapsed to a summary count with expandable `<details>` for the full list. Removed redundant "No — detection is model-free" column.

### TD-050: Model Classes table tok/s data not useful without per-user hardware context
**Status**: Partially resolved (Session 35)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Resolution**: Added "Speed values are approximate and vary significantly by hardware" caveat. Dynamic population from scan timing data deferred.

### TD-051: Compatibility matrix model list outdated (Sonnet 4 → 4.6)
**Status**: Resolved (Session 35)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Resolution**: Updated cloud-frontier example to "gpt-5.4, Claude Sonnet 4.6" in compatibility.py.

### TD-052: Compatibility page naming — consider "Detectors"
**Status**: Resolved (Session 35)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Resolution**: Nav link renamed to "Detectors." Both `/detectors` and `/compatibility` routes work (backward compat). Page itself still titled "Model-Detector Compatibility" for clarity.

### TD-054: VISION-LOCK growing beyond strategic scope
**Status**: Resolved (Session 34)
**Severity**: Medium
**Introduced**: Session 34 (user feedback)
**Description**: VISION-LOCK is 432 lines. The changelog alone is ~180 lines (41% of the document). It has drifted from a strategic document to a cumulative feature log. Sections like "What Exists Today" list every detector, every CLI command, every web feature — duplicating content from README and architecture docs.
**Impact**: The document no longer serves its strategic purpose efficiently. Hard to scan for product direction. Changelog adds noise with every version bump.
**Proposed resolution**: Prune VISION-LOCK to strategic content: problem, user, concept, constraints, invariants, success criteria, where-we're-going. Move "What Exists Today" detail to architecture/overview.md. Compress changelog to last 2 versions inline, archive older entries to git history. Target: <200 lines.
**Resolution**: Archived v4.9, wrote clean v5.0 at 132 lines. Document health rules added to AGENTS.md.

### TD-056: Tech debt file accumulates resolved items
**Status**: Resolved (Session 34)
**Severity**: Low
**Introduced**: Session 34 (user feedback)
**Description**: tech-debt.md is 315 lines. ~60% is resolved items. The active items are buried in the middle and end of the file.
**Impact**: Hard to scan for what's actually owed. Resolved items are useful history but obscure current state.
**Proposed resolution**: Move resolved items to a collapsed section at the bottom or a separate `tech-debt-resolved.md`. Active items at top, clearly separated.
**Resolution**: Restructured tech-debt.md — active items at top, resolved archived to tech-debt-resolved.md.

### TD-012: git-hotspots provides statistics without insight
**Status**: Resolved (Session 21)
**Severity**: Low
**Introduced**: Session 19 (identified via critical analysis)
**Description**: The git-hotspots detector correctly identifies high-churn files but doesn't explain *why* the churn matters. A file changed 50 times could be healthy (frequently improved) or problematic (constantly breaking). Without context about *what* changed, churn alone is weak signal.
**Impact**: Findings are technically accurate but not actionable. Developers see "this file changed a lot" and shrug.
**Resolution**: Enriched with commit message classification (fix/refactor/feature/other), author concentration analysis (bus-factor, coordination overhead), and actionable insights in descriptions. Bug-fix-heavy churn escalates severity. Evidence now includes commit type breakdown.

### TD-044: Dead-code JS/TS monorepo false positives
**Status**: Resolved (Session 31)
**Severity**: Medium
**Introduced**: Session 28 (multi-repo validation — shadcn-ui)
**Description**: The dead-code detector flags ~1700 FPs on shadcn-ui/ui. Remaining FPs come from non-auto-generated files where exports are consumed via dynamic `import()` patterns in other packages, registry-based component loading, and barrel re-exports.
**Impact**: Dead-code detector is unusable for JS/TS monorepos. ~99% FP rate.
**Resolution**: Added barrel re-export tracking (`export * from`, `export { } from`), TypeScript type export/import tracking, intra-file reference tracking for JS/TS, `import * as` namespace import handling, and package.json entry-point detection (main/exports/module/types). Entry-point files' exports are treated as public API. 7 new tests covering all patterns.

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

### TD-013: No CSRF protection on web UI
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added CSRF middleware (`src/sentinel/web/csrf.py`) using HMAC-signed tokens with per-process secrets. Cookie set on GET, validated via X-CSRF-Token header or form field on POST. SameSite=Strict. HTMX configured to auto-include token. All web tests updated with CSRF-aware test client.

### TD-014: No automated eval regression gate in CI
**Status**: Resolved (Session 24)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `sentinel eval tests/fixtures/sample-repo --json-output eval-result.json` step to `.github/workflows/ci.yml`. Runs after tests, exits non-zero if precision < 70% or recall < 90%. Eval result uploaded as CI artifact.

### TD-015: Unbounded historical fingerprint query
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: `get_known_fingerprints()` now accepts `retention_days` parameter (default 90). Query bounded with `WHERE created_at >= datetime('now', ?)`. Use 0 to disable bounding.

### TD-017: Entry-point plugin collision resolution is broken
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: `load_entrypoint_detectors()` now snapshots `builtin_classes = dict(_REGISTRY)` before loading entry-points and restores overwritten entries after loading. Collision detection is post-hoc but effective.

### TD-018: Mutable shared state in per-detector provider swap
**Status**: Resolved (Session 23)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `DetectorContext.with_config()` method that returns a shallow copy with config overrides. Runner now creates per-detector context copies instead of mutating `ctx.config` in-place. Eliminates temporal coupling and swap-restore pattern.

### TD-019: Inconsistent error model in ModelProvider protocol
**Status**: Resolved (Session 24)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Documented the error contract explicitly in the `ModelProvider` Protocol docstring. The asymmetry is intentional: `generate()` raises on failure (critical path — judge/detector calls must surface errors), `embed()` returns None (non-critical — context enrichment degrades gracefully), `check_health()` returns False. Each method's docstring now specifies its error behavior and expected exceptions.

### TD-020: No data lifecycle management for SQLite store
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `prune_old_data()` in store/findings.py with configurable retention_days. Deletes old llm_log, findings, annotations, runs, and persistence entries. Added `sentinel prune --older-than N` CLI command. Runs VACUUM after deletion.

### TD-021: `chunks` table has no repo scoping for scan-all
**Status**: Resolved (Session 24)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `repo_path` column to `chunks` table (migration v9). All CRUD functions in `store/embeddings.py` now accept `repo_path` parameter. Indexer threads `repo_root` through to storage and scopes `embed_meta` keys by repo. Context gatherer passes `repo_root` to `query_similar()`. Multi-repo isolation test added.

### TD-022: Migration framework lacks atomicity
**Status**: Resolved (Session 23)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Replaced `executescript()` with per-statement `execute()` calls within implicit transactions. Each migration + version stamp commits atomically. Rollback on failure. ALTER TABLE guarded with "duplicate column" tolerance for partial recovery.

### TD-023: No machine-readable `findings` command for past runs
**Status**: Resolved (Session 23)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `sentinel findings` CLI command with --run, --detector, --severity, --json-output options. Defaults to most recent run if --run not specified.

### TD-025: No CSRF, auth, or path validation on web scan endpoint
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: CSRF fixed via TD-013. Scan endpoint now resolves paths and validates against configurable `allowed_scan_roots` list. User-supplied paths checked with Path.resolve() to prevent traversal.

### TD-026: No retry logic for cloud model providers
**Status**: Resolved (Session 23)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added retry logic (2 retries with exponential backoff) to both OpenAICompatibleProvider and AzureProvider `generate()` methods. Respects Retry-After headers. Retries on 429, 500, 502, 503, 504, timeouts, and connection errors.

### TD-027: Hardcoded detector import list in runner
**Status**: Resolved (Session 23)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Replaced 14 hardcoded imports with `pkgutil.iter_modules()` over `sentinel.detectors` package. New detectors are auto-discovered — no runner changes needed.

### TD-028: LLM-assisted detector paths untested with mock providers
**Status**: Resolved (Session 23)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added 16 tests in `tests/detectors/test_llm_detector_paths.py` covering both semantic-drift and test-coherence LLM paths: valid JSON, malformed JSON, empty responses, provider errors, skip_llm, unhealthy provider, basic+enhanced modes.

### TD-029: Judge parse failures invisible in report
**Status**: Resolved (Session 23)
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Parse failures now set `judge_verdict = "inconclusive"` on the finding context. Report shows `❓ unverified` badge to distinguish from "judge confirmed" findings.

### TD-030: No confidence-based finding filtering
**Status**: Resolved (Session 24)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `min_confidence` config field (default 0.0). Findings below threshold are still persisted for audit trail but excluded from the morning report. Filtered count logged. Configurable via `sentinel.toml` or programmatically. 2 new tests.

### TD-031: File renames break fingerprints with no fuzzy fallback
**Status**: Resolved (Session 24)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review, extends OQ-003)
**Resolution**: Added `fuzzy_fingerprint` — path-free hash of (detector, category, normalized_content). Computed alongside strict fingerprint via `compute_fuzzy_fingerprint()`. Dedup checks fuzzy match when strict match fails, tagging findings as `recurring` + `fuzzy_match=True`. Suppression remains strict-fingerprint-only. Schema migration v10 adds column + index. 8 new tests.

### TD-033: External Google Font dependency in web UI
**Status**: Resolved (Session 24)
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Removed Google Fonts `<link>` tags from base.html. CSS body font changed to `system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif`. Mono fonts keep `'JetBrains Mono'` in stack (works if locally installed) with `monospace` fallback. Zero external network requests for typography.

### TD-034: No release/publish CI workflow
**Status**: Resolved (Session 24)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Created `.github/workflows/release.yml`. Triggers on `v*` tags. Builds wheel with `python -m build`, installs and smoke-tests the wheel, then publishes to PyPI via trusted publishing (OIDC, no API keys). Requires `pypi` environment to be configured in GitHub repo settings. Dependabot/pip-audit deferred — tracked separately if needed.

### TD-035: Stale egg-info checked into repo
**Status**: Resolved (Session 23)
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Already covered by `*.egg-info/` in .gitignore. The directory is not tracked by git (verified via `git ls-files`).

### TD-036: `num_ctx` is Ollama-specific but in protocol signature
**Status**: Resolved (Session 24)
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Documented in Protocol docstring that `num_ctx` is Ollama-only. Added notes in OpenAI and Azure `generate()` docstrings that it's accepted for protocol compatibility but ignored. The parameter remains in the protocol for Ollama's benefit.

### TD-037: Web UI shared sqlite3 connection across threads
**Status**: Resolved (Session 24)
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: `create_app()` now accepts `db_path` parameter for production use. When set, `_get_conn()` opens a fresh per-call connection with `check_same_thread=True`. `_open_db()` context manager ensures cleanup. Tests continue using shared `db_conn` for performance. CLI `serve` command passes `db_path` instead of shared connection.

### TD-038: Missing index on `runs.repo_path`
**Status**: Resolved (Session 23)
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `CREATE INDEX IF NOT EXISTS idx_runs_repo_path ON runs(repo_path)` in schema migration v8.

### TD-040: Dead-code detector misses intra-file symbol usage
**Status**: Resolved (Session 28)
**Severity**: Medium
**Introduced**: Session 27 (pip-tools real-world validation)
**Resolution**: Added `internal_refs` tracking to `_ModuleInfo` — `_parse_python_module` now walks the full AST collecting `ast.Name(ctx=Load)` and `ast.Attribute` references, and `_find_unused_python_symbols` skips symbols found in `internal_refs`. Also added PEP 517 build hooks to `_PYTHON_ALWAYS_USED`. Result: dead-code findings on pip-tools dropped from 6 FP to 0.

### TD-042: Unused-deps misses plugin/entry-point loading patterns
**Status**: Resolved (Session 28)
**Severity**: Medium
**Introduced**: Session 27 (pip-tools real-world validation)
**Resolution**: Three fixes: (1) Added `_TOOL_PACKAGE_PREFIXES` for prefix-based matching — any `pytest_*`, `flake8_*`, `pylint_*`, `mypy_*` package is treated as a tool extension. (2) Parse `[build-system].requires` from `pyproject.toml` and exclude those packages from the unused check. (3) Added `covdefaults`, `flit_core`, `setuptools_scm` to `_TOOL_PACKAGES`. Result: unused-deps findings on pip-tools dropped from 3 FP to 0.

## Won't Fix

(None yet)

