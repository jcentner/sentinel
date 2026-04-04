# Phase 1: MVP Core — Implementation Plan

> **Status**: Planning
> **Prerequisites**: Phase 0 complete, VISION-LOCK.md created, OQ-007 resolved (→ ADR-008)
> **Goal**: A runnable end-to-end pipeline: `sentinel scan <repo-path>` → detect → judge → dedup → morning report

## Acceptance Criteria

1. `sentinel scan <repo-path>` runs and produces a markdown morning report
2. At least 3 detectors produce findings: `todo-scanner`, `lint-runner`, `dep-audit`
3. Findings are stored in SQLite with fingerprinting and deduplication
4. LLM Judge (via Ollama) evaluates each finding when available; system degrades to raw findings without it
5. A second run on the same repo produces identical findings (repeatability for Tier 1 detectors)
6. `sentinel suppress <finding-id>` excludes a finding from future reports
7. `sentinel history` shows past runs
8. Morning report is scannable: one line per finding, expandable evidence, severity tags
9. All core modules have unit tests; detectors have both true-positive and false-positive test cases

## Project Structure

```
sentinel/
├── pyproject.toml              # Project config (dependencies, scripts, tool config)
├── README.md
├── src/
│   └── sentinel/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point (click/typer)
│       ├── config.py           # Configuration loading
│       ├── models.py           # Finding, Evidence, DetectorContext dataclasses
│       ├── core/
│       │   ├── __init__.py
│       │   ├── runner.py       # Orchestrates: detect → gather → judge → dedup → report
│       │   ├── context.py      # Context gatherer (simple file-proximity for MVP)
│       │   ├── judge.py        # LLM Judge via Ollama
│       │   ├── dedup.py        # Fingerprinting and deduplication
│       │   └── report.py       # Morning report generator (markdown)
│       ├── detectors/
│       │   ├── __init__.py
│       │   ├── base.py         # Detector ABC and registry
│       │   ├── todo_scanner.py # TODO/FIXME/HACK scanner with git blame age
│       │   ├── lint_runner.py  # ruff wrapper
│       │   └── dep_audit.py    # pip-audit wrapper
│       └── store/
│           ├── __init__.py
│           ├── db.py           # SQLite connection and migrations
│           ├── findings.py     # Finding CRUD operations
│           └── runs.py         # Run history tracking
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── test_models.py          # Finding/Evidence validation
│   ├── test_runner.py          # Pipeline integration tests
│   ├── test_dedup.py           # Fingerprinting tests
│   ├── test_report.py          # Report generation tests
│   ├── test_judge.py           # LLM Judge tests (mocked Ollama)
│   ├── test_store.py           # SQLite store tests
│   └── detectors/
│       ├── test_todo_scanner.py
│       ├── test_lint_runner.py
│       └── test_dep_audit.py
└── docs/                       # (existing docs tree)
```

## Implementation Slices

Ordered by dependency — each slice is independently testable and committable.

### Slice 1: Project Scaffolding
**Files**: `pyproject.toml`, `src/sentinel/__init__.py`
**What**: Set up the Python project with dependencies, entry points, and tool config (ruff, mypy, pytest).
**Dependencies**: pip, pip-audit, ruff, click, pytest
**Test**: `pip install -e .` succeeds, `sentinel --help` shows usage
**Commit**: `chore(project): initialize Python project scaffolding`

### Slice 2: Data Models
**Files**: `src/sentinel/models.py`, `tests/test_models.py`
**What**: Implement `Finding`, `Evidence`, `DetectorContext`, `RunSummary` as Python dataclasses matching the detector interface spec. Include validation (severity enum, confidence range, required fields).
**Test**: Unit tests for construction, validation, serialization
**Commit**: `feat(models): implement Finding and Evidence data models`

### Slice 3: SQLite State Store
**Files**: `src/sentinel/store/db.py`, `src/sentinel/store/findings.py`, `src/sentinel/store/runs.py`, `tests/test_store.py`
**What**: SQLite database with schema migrations. Tables: `runs`, `findings`, `suppressions`. CRUD for findings, run tracking, suppression flags.
**Schema**:
```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    repo_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    scope TEXT NOT NULL,         -- 'full', 'incremental', 'targeted'
    finding_count INTEGER DEFAULT 0
);

CREATE TABLE findings (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    fingerprint TEXT NOT NULL,   -- content-hash for dedup
    detector TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    file_path TEXT,
    line_start INTEGER,
    line_end INTEGER,
    evidence_json TEXT NOT NULL, -- JSON array of Evidence objects
    context_json TEXT,           -- detector-specific metadata
    status TEXT NOT NULL DEFAULT 'new', -- new, confirmed, suppressed, resolved, approved
    created_at TEXT NOT NULL
);

CREATE TABLE suppressions (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    reason TEXT,
    suppressed_at TEXT NOT NULL
);

CREATE INDEX idx_findings_fingerprint ON findings(fingerprint);
CREATE INDEX idx_findings_run_id ON findings(run_id);
CREATE INDEX idx_findings_status ON findings(status);
```
**Test**: CRUD operations, dedup queries, suppression filtering
**Commit**: `feat(store): implement SQLite state store with schema`

### Slice 4: Detector Base + Registry
**Files**: `src/sentinel/detectors/base.py`, `src/sentinel/detectors/__init__.py`
**What**: Abstract base class `Detector` with `detect(context: DetectorContext) -> list[Finding]`. Simple registry for discovering installed detectors.
**Test**: Registry finds registered detectors, base class enforces interface
**Commit**: `feat(detectors): implement detector base class and registry`

### Slice 5: TODO Scanner Detector
**Files**: `src/sentinel/detectors/todo_scanner.py`, `tests/detectors/test_todo_scanner.py`
**What**: Scan for TODO/FIXME/HACK/XXX comments. Extract line, file, surrounding context. Use `git blame` to determine age. Produce Finding objects with evidence.
**Test**: True positive (file with TODOs), false positive (TODO in test expectations, comments about "to do" in prose), empty repo
**Commit**: `feat(detector): implement todo-scanner with git blame age`

### Slice 6: Lint Runner Detector
**Files**: `src/sentinel/detectors/lint_runner.py`, `tests/detectors/test_lint_runner.py`
**What**: Run `ruff check` on the target repo, parse JSON output, normalize into Finding objects. Respect incremental scope (only changed files).
**Test**: Repo with lint errors, clean repo, ruff not installed (graceful error)
**Commit**: `feat(detector): implement lint-runner wrapping ruff`

### Slice 7: Dependency Audit Detector
**Files**: `src/sentinel/detectors/dep_audit.py`, `tests/detectors/test_dep_audit.py`
**What**: Run `pip-audit` on the target repo (if it has Python deps), parse JSON output, normalize into Finding objects.
**Test**: Repo with known vulnerability, clean repo, no Python project (skip gracefully)
**Commit**: `feat(detector): implement dep-audit wrapping pip-audit`

### Slice 8: Finding Fingerprinting + Dedup
**Files**: `src/sentinel/core/dedup.py`, `tests/test_dedup.py`
**What**: Compute content-based fingerprints: `hash(detector_name, category, file_path, key_content_normalized)`. Compare against state store to identify new/recurring/resolved findings. Filter suppressed.
**Test**: Same finding across runs → same fingerprint, different findings → different fingerprints, suppressed findings filtered, line number changes don't break fingerprint
**Commit**: `feat(core): implement finding fingerprinting and deduplication`

### Slice 9: Context Gatherer (Simple)
**Files**: `src/sentinel/core/context.py`
**What**: For each finding, gather: the file content around the finding location, related test/doc files (by naming convention), recent git log for the file. No embeddings for MVP — simple file-proximity heuristic.
**Test**: Gathers correct surrounding code, finds related test file, handles missing files gracefully
**Commit**: `feat(core): implement simple file-proximity context gatherer`

### Slice 10: LLM Judge
**Files**: `src/sentinel/core/judge.py`, `tests/test_judge.py`
**What**: Send each finding + context to Ollama. Structured prompt asking: is this real? severity? evidence summary? Return enriched finding. Graceful degradation when Ollama is unavailable (pass through raw findings).
**Test**: Mock Ollama responses, test prompt construction, test degraded mode
**Commit**: `feat(core): implement LLM judge via Ollama`

### Slice 11: Morning Report Generator
**Files**: `src/sentinel/core/report.py`, `tests/test_report.py`
**What**: Generate markdown report from judged + deduped findings. Format: summary stats, one line per finding, expandable evidence blocks. Group by severity, then category.
**Test**: Report with findings, empty report, report formatting matches spec
**Commit**: `feat(core): implement markdown morning report generator`

### Slice 12: Pipeline Runner
**Files**: `src/sentinel/core/runner.py`, `tests/test_runner.py`
**What**: Orchestrate the full pipeline: create run record → run detectors → gather context → judge → dedup → generate report → update run record. Handle errors per-detector (one failing detector doesn't abort the run).
**Test**: Integration test with mock detectors, test error isolation
**Commit**: `feat(core): implement pipeline runner orchestration`

### Slice 13: CLI
**Files**: `src/sentinel/cli.py`, `src/sentinel/config.py`
**What**: Click-based CLI with commands: `scan`, `suppress`, `approve`, `history`, `--help`. Config loading from `sentinel.toml` or CLI flags (repo path, model name, output path).
**Test**: CLI smoke test, `--help` output, config precedence
**Commit**: `feat(cli): implement CLI with scan/suppress/history commands`

### Slice 14: End-to-End Integration Test
**Files**: `tests/test_integration.py`
**What**: Create a temporary test repo with known issues (TODOs, lint errors). Run full pipeline. Assert findings appear in report. Run again, assert dedup works. Suppress a finding, assert it's excluded.
**Test**: This IS the test
**Commit**: `test(integration): add end-to-end pipeline test`

### Slice 15: Repeatability Test
**Files**: `tests/test_repeatability.py`
**What**: Run pipeline twice on identical repo state, assert byte-identical output for deterministic detectors. This validates ADR-008's repeatability requirement.
**Test**: This IS the test
**Commit**: `test(eval): add repeatability verification test`

## Dependencies (Python Packages)

| Package | Purpose | Version Constraint |
|---------|---------|-------------------|
| `click` | CLI framework | ≥ 8.0 |
| `ruff` | Python linter (used by lint-runner detector) | ≥ 0.4 |
| `pip-audit` | Dependency vulnerability scanner | ≥ 2.7 |
| `httpx` | HTTP client for Ollama API | ≥ 0.27 |
| `pytest` | Testing | ≥ 8.0 |
| `pytest-tmp-files` | Temp file fixtures | any |

## Open Questions for Phase 1

| Question | Current Answer | May Revisit |
|----------|---------------|-------------|
| Embeddings in MVP? | No — simple file-proximity context. Embeddings deferred to Phase 2. | Yes, if judge quality is poor |
| Which linter to wrap? | ruff only (Python-focused). Others later. | Yes, may add ESLint for JS repos |
| Config format? | `sentinel.toml` via Python stdlib tomllib | Unlikely |
| Async detectors? | No — run sequentially in MVP. Async later if needed. | Yes |

## Phase 1 Completion Checklist

- [ ] All 15 slices implemented and committed
- [ ] All tests pass (`pytest` green)
- [ ] Type checking passes (`mypy` or `pyright` clean)
- [ ] Linting passes (`ruff check` clean)
- [ ] `sentinel scan` works against at least one real repo
- [ ] Morning report generated and reviewed for scannability
- [ ] Repeatability test passes
- [ ] Docs updated to reflect implemented state
- [ ] ADRs recorded for any decisions made during implementation
- [ ] Phase marked complete in roadmap
