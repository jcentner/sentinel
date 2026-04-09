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

### TD-013: No CSRF protection on web UI
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added CSRF middleware (`src/sentinel/web/csrf.py`) using HMAC-signed tokens with per-process secrets. Cookie set on GET, validated via X-CSRF-Token header or form field on POST. SameSite=Strict. HTMX configured to auto-include token. All web tests updated with CSRF-aware test client.

### TD-014: No automated eval regression gate in CI
**Status**: Active
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Description**: The eval system can produce precision/recall metrics, but there is no CI step that gates on these metrics. A detector regression (lower precision, new FPs) would only be caught by manual inspection of `sentinel eval-history`.
**Impact**: Quality regressions can ship undetected. The eval system measures but doesn't protect.
**Proposed resolution**: Add a CI step that runs `sentinel eval` against the sample-repo fixture and fails the build if precision or recall drops below configured thresholds. The `eval` command already exits non-zero on target miss — just needs CI integration.

### TD-015: Unbounded historical fingerprint query
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: `get_known_fingerprints()` now accepts `retention_days` parameter (default 90). Query bounded with `WHERE created_at >= datetime('now', ?)`. Use 0 to disable bounding.

### TD-016: Serial LLM judge bottleneck
**Status**: Active
**Severity**: Medium
**Introduced**: Phase 1 (supersedes aspect of TD-002)
**Description**: The judge calls `provider.generate()` sequentially for each finding at ~4s/call. 50 findings = 3.3 min, 100 = 7 min. Combined with synthesis (~40s for 10 clusters), total LLM wall time is 7+ min for moderate repos.
**Impact**: Morning report latency scales linearly with finding count. Tolerable for small repos but a bottleneck for repos with 50+ findings.
**Proposed resolution**: Near-term: batch 3-5 findings per judge prompt to cut per-call overhead. Medium-term: async/concurrent judge calls (related to TD-002). Long-term: skip judge for high-confidence deterministic findings (confidence ≥ 0.95).

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
**Status**: Active
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Description**: `generate()` propagates httpx exceptions (via `raise_for_status()`), while `embed()` catches all exceptions and returns `None`. Every caller of `generate()` reimplements the same try/except pattern (judge, semantic-drift, test-coherence).
**Impact**: A forgotten try/except on `generate()` in new code will crash the scan on a network blip. Split error contract is a maintenance trap.
**Proposed resolution**: Document the contract explicitly in the Protocol docstring. Consider evolving to a result type with an error field, or making `generate()` catch and return `None` for transient failures (matching `embed()`).

### TD-020: No data lifecycle management for SQLite store
**Status**: Resolved (Session 23)
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `prune_old_data()` in store/findings.py with configurable retention_days. Deletes old llm_log, findings, annotations, runs, and persistence entries. Added `sentinel prune --older-than N` CLI command. Runs VACUUM after deletion.

### TD-021: `chunks` table has no repo scoping for scan-all
**Status**: Active
**Severity**: High
**Introduced**: Session 22 (identified via systemic review)
**Description**: The `chunks` table stores embeddings keyed by `file_path` with no `repo_path` column. In `scan-all` with a shared database, two repos with identically-named files (e.g., `src/main.py`) collide — indexing repo A deletes repo B's chunks via `upsert_chunks`.
**Impact**: Embedding-based context gathering produces corrupt results for `scan-all` users with overlapping file paths. Data loss is silent.
**Proposed resolution**: Add a `repo_path` column to the `chunks` table (schema migration v8). Scope all chunk queries by repo. Alternatively, document that `scan-all` doesn't support embedding indexes and skip indexing in multi-repo mode.

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

### TD-024: `--json-output` error envelope inconsistency
**Status**: Active
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Description**: JSON output shapes differ by command and by success/failure. Some error paths write to stderr with no JSON (e.g., `create-issues` with no config). Exit codes conflate "below target" with "errored" (eval uses exit 1 for both). No consistent envelope like `{"ok": true, "data": ...}`.
**Impact**: Agents must special-case each command's output format. Reduces reliability of automated Sentinel consumption.
**Proposed resolution**: Define and document a standard JSON envelope for all `--json-output` commands. Use distinct exit codes for "ran but below threshold" (e.g., exit 2) vs. "command errored" (exit 1).

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
**Status**: Active
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Description**: The judge marks likely FPs with confidence ≤ 0.3 and the report shows `⚠️ FP?` badges, but all findings still appear in the report body and count toward the total. No configurable threshold filters low-confidence findings before reporting.
**Impact**: Contradicts the <2-minute scannability target. A run with 30 findings where 10 are `FP?` still shows 30 items to scan.
**Proposed resolution**: Add configurable `min_confidence` threshold (e.g., 0.4) between judge and persistence. Low-confidence findings stored as `SUPPRESSED` for audit trail but excluded from the morning report.

### TD-031: File renames break fingerprints with no fuzzy fallback
**Status**: Active
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review, extends OQ-003)
**Description**: Fingerprints include `file_path` in the hash input. After `git mv src/foo.py src/bar.py`, every finding for that file appears as "new" in the next run, even if nothing else changed.
**Impact**: A refactor that renames 10 files floods the morning report with "new" findings that are actually recurring. Directly increases noise and review time.
**Proposed resolution**: Add a fuzzy fingerprint (detector + category + content, no path) for cross-run recurrence detection. The strict fingerprint (includes path) remains for within-run dedup. Fuzzy match marks findings as `recurring` to prevent false novelty but doesn't suppress.

### TD-032: Synthesis gated to standard+ tier, off by default
**Status**: Active
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Description**: Finding cluster synthesis requires `model_capability >= standard`. Since the default model is Qwen3.5 4B (`basic` tier), synthesis is disabled for most users. The noise-reduction step that collapses N symptoms into 1 root cause simply doesn't run in the default configuration.
**Impact**: Default users get noisier reports than the system is capable of producing. Pattern-based clustering in report.py partially compensates but lacks root-cause annotation.
**Proposed resolution**: Consider a simplified synthesis prompt ("are these the same issue?" → yes/no) that could work at `basic` tier. Reserve full root-cause analysis for `standard+`.

### TD-033: External Google Font dependency in web UI
**Status**: Active
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Description**: `base.html` loads Bricolage Grotesque and JetBrains Mono from Google Fonts over HTTPS. This contradicts the "works offline" spirit of local-first design.
**Impact**: Web UI typography breaks when offline. Inconsistent with the product's local-first promise.
**Proposed resolution**: Bundle the font files as static assets in the web package, or degrade gracefully to system fonts when offline.

### TD-034: No release/publish CI workflow
**Status**: Active
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Description**: No `.github/workflows/release.yml` exists. CI installs in editable mode only — no wheel build test, no installation-from-wheel smoke test, no PyPI publish step. No security scanning (Dependabot, CodeQL, pip-audit) on Sentinel's own dependencies.
**Impact**: Packaging bugs won't surface until a user does `pip install local-repo-sentinel`. No path to automated releases. Blocks PyPI publication goal.
**Proposed resolution**: (1) Add a release workflow: build wheel → install in clean venv → run smoke test → publish on tag. (2) Add Dependabot config. (3) Run `pip-audit` on Sentinel's own deps in CI.

### TD-035: Stale egg-info checked into repo
**Status**: Resolved (Session 23)
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Already covered by `*.egg-info/` in .gitignore. The directory is not tracked by git (verified via `git ls-files`).

### TD-036: `num_ctx` is Ollama-specific but in protocol signature
**Status**: Active
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Description**: `num_ctx` (Ollama context window size) is accepted by all three providers in `generate()` but silently ignored by OpenAI and Azure. A user configuring `num_ctx = 8192` for their Azure provider gets no feedback.
**Impact**: Configuration that appears to work but has no effect. Violates principle of least surprise.
**Proposed resolution**: Document that `num_ctx` is Ollama-only and ignored by other providers. Add a log warning in cloud providers when `num_ctx` is non-default.

### TD-037: Web UI shared sqlite3 connection across threads
**Status**: Active
**Severity**: Medium
**Introduced**: Session 22 (identified via systemic review)
**Description**: `create_app()` in `web/app.py` takes a single `sqlite3.Connection` stored on `app.state`. All request handlers share it. SQLite serializes writes. If a user triggers a scan from the web UI while another request writes, they contend on the same connection.
**Impact**: Potential write contention or `OperationalError: database is locked` under concurrent web use. Already uses `check_same_thread=False` indicating awareness.
**Proposed resolution**: Switch to a connection-per-request factory or a connection pool. Each request opens and closes its own connection.

### TD-038: Missing index on `runs.repo_path`
**Status**: Resolved (Session 23)
**Severity**: Low
**Introduced**: Session 22 (identified via systemic review)
**Resolution**: Added `CREATE INDEX IF NOT EXISTS idx_runs_repo_path ON runs(repo_path)` in schema migration v8.

## Won't Fix

(None yet)
