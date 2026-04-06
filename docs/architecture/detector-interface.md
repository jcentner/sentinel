# Detector Interface Specification

> **Status**: Active — reflects implementation as of 2026-04-05.

## Design principle

Every detector — whether a lint wrapper, a git-history analyzer, a docs-drift checker, or an LLM-assisted reviewer — produces findings through the same interface. This makes detectors pluggable, testable, and composable.

## Finding schema

Every detector outputs zero or more `Finding` objects:

```
Finding:
  detector:     string        # Which detector produced this (e.g., "lint-runner", "todo-scanner")
  category:     string        # Finding category (see categories below)
  severity:     "low" | "medium" | "high" | "critical"
  confidence:   float         # 0.0–1.0, how confident the detector is
  title:        string        # One-line summary
  description:  string        # Detailed explanation
  file_path:    string | null # Relative path to the affected file
  line_start:   int | null    # Optional start line
  line_end:     int | null    # Optional end line
  evidence:     Evidence[]    # Supporting evidence items
  context:      object | null # Additional detector-specific metadata
  fingerprint:  string        # Content-hash for dedup (assigned post-construction by the pipeline, not by detectors)
  status:       FindingStatus # Lifecycle state: new, confirmed, approved, suppressed, resolved
  timestamp:    datetime      # When the finding was produced
  id:           int | null    # Database primary key, assigned after storage
```

## Evidence schema

```
Evidence:
  type:     "code" | "doc" | "test" | "config" | "git_history" | "lint_output" | "audit_output" | "diff"
  source:   string        # File path or description
  content:  string        # The actual evidence text/snippet
  line_range: [int, int] | null
```

## Finding categories

| Category | Description | Example detectors |
|----------|-------------|-------------------|
| `docs-drift` | Inconsistency between documentation and code/config/other docs | Docs-drift detector |
| `code-quality` | Lint findings, complexity, dead code | ESLint, ruff, Semgrep |
| `test-health` | Test failures, flaky tests, coverage gaps | Test runner, coverage diff |
| `dependency` | Outdated deps, known vulnerabilities, audit findings | npm audit, pip-audit |
| `todo-fixme` | TODO/FIXME/HACK/XXX comments, especially old or concerning ones | Grep/regex scanner |
| `security` | Potential security issues surfaced by detectors | Semgrep, custom rules |
| `performance` | Performance anti-patterns (e.g., SQL without CTEs, N+1 patterns) | SQLFluff + LLM, custom |
| `config-drift` | Configuration inconsistencies across environments or files | Config comparator |
| `git-health` | Hotspots, high churn, long-lived branches, merge conflict patterns | Git history analyzer |

## Detector contract

Each detector implements:

```
interface Detector:
  name:        string
  description: string
  tier:        "deterministic" | "heuristic" | "llm-assisted"
  categories:  string[]           # Which categories it can produce
  
  detect(context: DetectorContext) -> Finding[]
```

Where `DetectorContext` provides:

```
DetectorContext:
  repo_root:    string            # Absolute path to repo root
  scope:        "full" | "incremental" | "targeted"
  changed_files: string[] | null  # For incremental runs
  target_paths:  string[] | null  # For targeted runs
  config:       object            # Detector-specific configuration
  conn:         Connection | null # Optional SQLite connection for LLM interaction logging
  run_id:       int | null        # Current run ID for LLM log entries
```

> **Note**: The original spec included `previous_run: RunSummary | null` in DetectorContext for delta/trend detection. This is not yet implemented. Git-hotspots works without it by querying git log directly.

## Planned detectors (MVP)

| Detector | Tier | Categories | Status | Description |
|----------|------|------------|--------|-------------|
| `lint-runner` | Deterministic | code-quality | ✅ Implemented | Wraps ruff for Python linting and normalizes output |
| `eslint-runner` | Deterministic | code-quality | ✅ Implemented | Wraps ESLint/Biome for JS/TS linting (tries Biome first, falls back to ESLint) |
| `go-linter` | Deterministic | code-quality | ✅ Implemented | Wraps golangci-lint for Go linting with security linter elevation |
| `rust-clippy` | Deterministic | code-quality | ✅ Implemented | Wraps cargo clippy for Rust linting with correctness/suspicious elevation |
| `todo-scanner` | Deterministic | todo-fixme | ✅ Implemented | Grep for TODO/FIXME/HACK with age from git blame |
| `dep-audit` | Deterministic | dependency | ✅ Implemented | Wraps npm audit, pip-audit |
| `docs-drift` | Deterministic + LLM | docs-drift | ✅ Implemented | Compares docs ↔ code, docs ↔ docs for consistency |
| `git-hotspots` | Heuristic | git-health | ✅ Implemented | Identifies high-churn files via statistical outlier analysis on git log |
| `complexity` | Deterministic | code-quality | ✅ Implemented | Flags functions exceeding cyclomatic complexity threshold |

### docs-drift implementation notes

The docs-drift detector has three detection modes:

1. **Stale reference detection** (deterministic): Broken markdown links and missing inline code paths, with dual resolution (doc-relative and repo-root-relative).
2. **Dependency drift** (deterministic): Compares `pip install`/`npm install` commands in key docs (README, CONTRIBUTING, INSTALL) against `pyproject.toml`/`requirements.txt`/`package.json`.
3. **Doc-code comparison** (LLM-assisted, optional): Uses Ollama to compare code blocks in key docs against actual source files. Gracefully degrades when Ollama is unavailable.

The tier is `LLM_ASSISTED` because the LLM comparison is available, but the primary signal comes from deterministic checks (modes 1 and 2). LLM comparison is limited to key documentation files to bound cost per scan.

## Planned detectors (Phase 2+)

| Detector | Tier | Categories | Status | Description |
|----------|------|------------|--------|-------------|
| `test-runner` | Deterministic | test-health | Planned | Runs test suite, captures failures |
| `sql-antipattern` | Deterministic + LLM | performance | Planned | SQLFluff + LLM for semantic suggestions (CTE, N+1) |
| `semgrep-runner` | Deterministic | security, code-quality | Planned | Wraps Semgrep with custom rules |
| `dead-code` | Heuristic | code-quality | Planned | Tree-sitter reachability analysis |
| `config-drift` | Deterministic | config-drift | Planned | Compare env configs, schema vs. defaults |
| `complexity` | Heuristic | code-quality | ✅ Implemented | Cyclomatic complexity, function length |

## Custom detectors

Sentinel supports loading user-defined detectors from a directory configured via `detectors_dir` in `sentinel.toml`. Each `.py` file in the directory is dynamically imported at scan time. Any class extending `Detector` is auto-registered via `__init_subclass__` and participates in the scan.

Requirements:
- File must be a valid Python module (not starting with `_`)
- Detector class must extend `sentinel.detectors.base.Detector`
- Must implement: `name`, `description`, `tier`, `categories`, `detect()`
- `detect()` should return `list[Finding]` and never raise

See the README for a concrete example.

## Docs-drift detector: detailed design

This is a first-class detector category because:
- It's a **comparison task**, not open-ended generation. The model gets two texts and answers: "do these agree?"
- The evidence is concrete: here's the README saying X, here's the code doing Y.
- It's something humans chronically neglect and existing linters can't catch.
- It scales across the repo naturally.

### Specific patterns to detect

| Pattern | Source A | Source B | Method |
|---------|----------|----------|--------|
| Install instructions drift | README / CONTRIBUTING | package.json scripts, actual deps | Parse + compare |
| API docs drift | JSDoc, OpenAPI spec | Actual function signatures/behavior | AST extraction + compare |
| Config docs drift | Docs describing config | Actual config schema / defaults | Parse + compare |
| Changelog drift | CHANGELOG entries | Git history | Compare entries vs. commits |
| Stale references | Any doc | File system | Check referenced files/functions exist |
| Architecture drift | Architecture docs (data flow) | Import graph | Graph extraction + compare |
| Cross-doc contradiction | Doc A | Doc B | LLM comparison |

### Method

1. **Deterministic extraction**: Parse docs structure, extract code blocks, file references, function names, CLI examples. Parse code AST, extract exports, signatures, config schemas.
2. **LLM comparison**: For each (doc-claim, code-reality) pair, ask the model: "Does this documentation accurately describe this code? If not, what's wrong?"
3. **Confidence scoring**: Deterministic mismatches (dead reference, missing file) get high confidence. Semantic judgment calls get lower confidence, flagged for human review.
