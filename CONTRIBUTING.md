# Contributing to Local Repo Sentinel

## Development Setup

```bash
git clone <repo-url> && cd sentinel
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web,detectors]"
```

Verify your setup:

```bash
sentinel doctor          # Check external tool availability
python -m pytest -q      # Run tests
ruff check src/ tests/   # Lint
mypy src/sentinel/ --strict  # Type check
```

## Project Structure

```
src/sentinel/
├── cli.py                  # Click CLI entry point
├── config.py               # sentinel.toml loader
├── models.py               # Finding, Evidence dataclasses
├── core/
│   ├── runner.py           # Pipeline orchestrator
│   ├── context.py          # Evidence gatherer (file-proximity + embeddings)
│   ├── judge.py            # LLM judge via Ollama
│   ├── dedup.py            # Fingerprinting and deduplication
│   ├── report.py           # Markdown report generator
│   ├── clustering.py       # Pattern + directory clustering
│   └── eval.py             # Precision/recall evaluation
├── detectors/
│   ├── base.py             # Detector ABC + auto-registry
│   ├── todo_scanner.py     # TODO/FIXME scanner
│   ├── lint_runner.py      # ruff wrapper
│   ├── eslint_runner.py    # ESLint/Biome wrapper
│   ├── go_linter.py        # golangci-lint wrapper
│   ├── rust_clippy.py      # cargo clippy wrapper
│   ├── dep_audit.py        # pip-audit wrapper
│   ├── docs_drift.py       # Documentation drift detector
│   ├── git_hotspots.py     # Git churn analysis
│   └── complexity.py       # Cyclomatic complexity
├── store/
│   ├── db.py               # SQLite connection + migrations
│   ├── findings.py         # Finding CRUD
│   ├── runs.py             # Run history
│   └── eval_store.py       # Eval results persistence
└── web/
    ├── app.py              # Starlette web UI
    ├── templates/           # Jinja2 templates
    └── static/              # CSS, JS, htmx
```

## Adding a Detector

Detectors auto-register via `__init_subclass__`. Create a new file in `src/sentinel/detectors/`:

```python
from sentinel.detectors.base import Detector
from sentinel.models import DetectorContext, DetectorTier, Finding, Severity

class MyDetector(Detector):
    @property
    def name(self) -> str:
        return "my-detector"

    @property
    def description(self) -> str:
        return "What this detector does"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        # Your detection logic here
        return []
```

Key conventions for detectors:
- Return `[]` when the detector doesn't apply (wrong language, tool missing)
- Catch `FileNotFoundError` for external tools and log at `warning` level
- Include an outer `try/except Exception` safety net with `logger.exception()`
- Support `context.scope` for incremental and targeted scans
- Every finding needs evidence — never return a finding without it

## Testing

Tests live in `tests/` mirroring the source structure. Detector tests go in `tests/detectors/`.

```bash
# Run all tests
python -m pytest -q

# Run specific test file
python -m pytest tests/test_cli.py -v

# Run a specific test class
python -m pytest tests/test_cli.py::TestScanCommand -v
```

Every detector should have:
- True positive tests (finds real issues)
- False positive tests (doesn't flag clean code)
- Tests for incremental and targeted scope handling
- Tests for missing external tools (graceful skip)

## Code Style

- **Lint**: `ruff check src/ tests/`
- **Types**: `mypy src/sentinel/ --strict`
- Python 3.11+ (no 3.10 backcompat needed)
- Prefer simple, tested code over clever abstractions
- No `from __future__ import annotations` in `config.py` (dataclass field introspection)

## Commit Messages

Use [conventional commits](https://www.conventionalcommits.org/):

```
feat(detector): add my-detector for X
fix(web): resolve XSS in annotation rendering
test(detector): add false positive cases for my-detector
docs(architecture): update detector interface spec
refactor(cli): extract scan helpers
chore(ci): add Python 3.13 to test matrix
```

## Architecture Decisions

Significant design choices are recorded as ADRs in `docs/architecture/decisions/`. Check existing ADRs before proposing changes that might conflict with established decisions.

Key invariants:
1. Detectors are pluggable — never change the pipeline to add a detector
2. LLM is replaceable — model names are config, not code
3. Evidence is mandatory — no finding without concrete evidence
4. Human approval gates external actions
5. Local-first — no cloud dependencies except optional GitHub API
