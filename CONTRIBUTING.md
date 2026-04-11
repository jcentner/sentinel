# Contributing to Local Repo Sentinel

## Development Setup

```bash
git clone https://github.com/jcentner/sentinel.git && cd sentinel
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

## Codebase Reading Guide

New to the codebase? Read these files in order to understand how Sentinel works:

1. **`src/sentinel/models.py`** — Core data types (`Finding`, `Evidence`, `DetectorContext`). Everything flows through these.
2. **`src/sentinel/detectors/base.py`** — The `Detector` ABC and auto-registry. Shows the contract every detector implements.
3. **`src/sentinel/detectors/todo_scanner.py`** — The simplest detector. Read this as a concrete example before the abstract interfaces.
4. **`src/sentinel/core/runner.py`** — The pipeline orchestrator. Shows how detectors → fingerprint → dedup → judge → report fit together.
5. **`src/sentinel/core/provider.py`** — The `ModelProvider` protocol and factory. How LLM calls are abstracted.
6. **`src/sentinel/cli.py`** — All user-facing commands. Entry point for understanding what the tool does from a user perspective.

For deeper dives:
- **Store layer**: Start with `store/db.py` (migrations), then `store/findings.py` (CRUD)
- **LLM paths**: `core/judge.py` → `core/synthesis.py` → `core/context.py`
- **Eval system**: `core/eval.py` → `core/benchmark.py` (benchmark reuses eval's `evaluate()`)
- **Web UI**: `web/app.py` (routes) → `web/templates/` (Jinja2)

## Project Structure

```
src/sentinel/
├── __main__.py             # python -m sentinel entry point
├── cli.py                  # Click CLI entry point
├── config.py               # sentinel.toml loader
├── github.py               # GitHub issue creation
├── models.py               # Finding, Evidence dataclasses
├── core/
│   ├── runner.py           # Pipeline orchestrator
│   ├── context.py          # Evidence gatherer (file-proximity + embeddings)
│   ├── judge.py            # LLM judge
│   ├── synthesis.py        # Finding cluster synthesis (standard+ tier)
│   ├── dedup.py            # Fingerprinting and deduplication
│   ├── report.py           # Markdown report generator
│   ├── clustering.py       # Pattern + directory clustering
│   ├── provider.py         # ModelProvider protocol + factory
│   ├── eval.py             # Precision/recall evaluation
│   ├── benchmark.py        # Detector benchmarking
│   ├── indexer.py          # Embedding index builder
│   ├── ollama.py           # Ollama API client (low-level)
│   └── providers/
│       ├── ollama.py       # OllamaProvider
│       ├── openai_compat.py # OpenAI-compatible provider
│       ├── azure.py        # Azure AI Foundry provider (Entra ID)
│       └── replay.py       # ReplayProvider + RecordingProvider for eval
├── detectors/
│   ├── base.py             # Detector ABC + auto-registry + plugin loading
│   ├── complexity.py       # Cyclomatic complexity
│   ├── dead_code.py        # Unused exported symbols
│   ├── dep_audit.py        # pip-audit wrapper
│   ├── docs_drift.py       # Documentation drift detector
│   ├── eslint_runner.py    # ESLint/Biome wrapper
│   ├── git_hotspots.py     # Git churn analysis
│   ├── go_linter.py        # golangci-lint wrapper
│   ├── lint_runner.py      # ruff wrapper
│   ├── rust_clippy.py      # cargo clippy wrapper
│   ├── semantic_drift.py   # Semantic docs-drift (LLM, basic+ tier)
│   ├── stale_env.py        # .env.example drift detection
│   ├── test_coherence.py   # Test-code coherence (LLM, basic+ tier)
│   ├── todo_scanner.py     # TODO/FIXME scanner
│   └── unused_deps.py      # Unused declared dependencies
├── store/
│   ├── db.py               # SQLite connection + migrations
│   ├── findings.py         # Finding CRUD
│   ├── runs.py             # Run history
│   ├── eval_store.py       # Eval results persistence
│   ├── embeddings.py       # Embedding vector storage
│   ├── llm_log.py          # LLM interaction logging
│   └── persistence.py      # State persistence helpers
└── web/
    ├── app.py              # Starlette web UI
    ├── csrf.py             # HMAC-based CSRF protection
    ├── templates/           # Jinja2 templates
    └── static/              # CSS, JS, htmx
```

## Adding a Detector

Detectors auto-register via `__init_subclass__`. There are two paths:
- **Built-in detector** (PR to this repo): create a file in `src/sentinel/detectors/` — it is auto-discovered
- **External plugin** (separate pip package): publish with an `entry_points` declaration

### Minimal implementation

Create `src/sentinel/detectors/my_detector.py`:

```python
import logging
from pathlib import Path

from sentinel.detectors.base import COMMON_SKIP_DIRS, Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
    ScopeType,
)

logger = logging.getLogger(__name__)


class MyDetector(Detector):
    @property
    def name(self) -> str:
        return "my-detector"

    @property
    def description(self) -> str:
        return "One-line description shown in 'sentinel init --list-detectors'"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC  # or HEURISTIC, LLM_ASSISTED

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]  # see detector-interface.md for valid categories

    # Override capability_tier ONLY if your detector uses an LLM:
    # @property
    # def capability_tier(self) -> CapabilityTier:
    #     return CapabilityTier.BASIC  # or STANDARD, ADVANCED

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._scan(context)
        except Exception:
            logger.exception("%s failed", self.name)
            return []

    def _scan(self, context: DetectorContext) -> list[Finding]:
        root = Path(context.repo_root)
        files = self._collect_files(context, root)
        findings: list[Finding] = []

        for path in files:
            # ... detection logic ...
            findings.append(Finding(
                detector=self.name,
                category="code-quality",
                severity=Severity.MEDIUM,
                confidence=0.8,
                title="Issue found in function X",
                description="Detailed explanation of the problem",
                file_path=str(path.relative_to(root)),
                line_start=42,
                evidence=[
                    Evidence(
                        type=EvidenceType.CODE,
                        source=str(path.relative_to(root)),
                        content="the relevant code snippet",
                        line_range=(40, 50),
                    )
                ],
            ))

        return findings

    def _collect_files(self, context: DetectorContext, root: Path) -> list[Path]:
        """Collect files respecting scan scope."""
        # Incremental: only scan changed files
        if context.scope == ScopeType.INCREMENTAL and context.changed_files:
            return [
                root / f for f in context.changed_files
                if f.endswith(".py") and (root / f).is_file()
            ]

        # Targeted: only scan files under target paths
        if context.scope == ScopeType.TARGETED and context.target_paths:
            files = []
            for target in context.target_paths:
                tp = Path(target)
                if tp.is_file() and tp.suffix == ".py":
                    files.append(tp)
                elif tp.is_dir():
                    files.extend(tp.rglob("*.py"))
            return files

        # Full scan: walk the repo, skip common directories
        return [
            p for p in root.rglob("*.py")
            if not any(skip in p.parts for skip in COMMON_SKIP_DIRS)
        ]
```

### Auto-discovery

Built-in detectors are **auto-discovered** — the runner uses `pkgutil.iter_modules()` to find and import all modules in `src/sentinel/detectors/`. Simply creating a file with a `Detector` subclass in that directory is enough. No manual import or registration step is needed.

### PR checklist

| File | Change | Required? |
|------|--------|-----------|
| `src/sentinel/detectors/my_detector.py` | New detector implementation | Yes |
| `tests/detectors/test_my_detector.py` | Tests (see Testing below) | Yes |
| `docs/architecture/detector-interface.md` | Add row to detector table | Yes |
| `pyproject.toml` | Add external tool to `[project.optional-dependencies]` | If wrapping an external tool |
| `docs/reference/glossary.md` | Define new terms | If introducing new concepts |

### Incremental and targeted scan support

Every detector must handle three scan scopes. The standard pattern (shown in the template above):

| Scope | `context` fields | Detector behavior |
|-------|-------------------|--------------------|
| `FULL` | — | Walk the entire repo, skip `COMMON_SKIP_DIRS` |
| `INCREMENTAL` | `changed_files` = list of relative paths from `git diff` | Only process files in the changed list (filter by extension) |
| `TARGETED` | `target_paths` = list of absolute paths from `--target` | Only process files under the target paths |

If your detector wraps an external tool that can't easily be scoped (e.g., `pip-audit` audits the whole project), run the full tool but note in the detector that incremental mode is a no-op. The pipeline handles dedup regardless.

### Capability tiers

If your detector uses an LLM (via `context.config["provider"]`), declare the minimum model tier:

| Tier | When to use | Example |
|------|-------------|---------|
| `CapabilityTier.NONE` | No LLM needed (default) | lint-runner, todo-scanner |
| `CapabilityTier.BASIC` | Binary signal from a small model (4B+) | semantic-drift, test-coherence |
| `CapabilityTier.STANDARD` | Structured reasoning, multiple fields | Enhanced modes with specific gaps/actions |
| `CapabilityTier.ADVANCED` | Deep multi-artifact analysis | Intent comparison, arch drift (planned) |

The runner **warns but does not block** if the user's configured model is below your declared tier. Your detector should still function — degrade gracefully by returning simpler output or skipping the LLM path entirely. Check the tier at runtime:

```python
from sentinel.models import CapabilityTier

cap = context.config.get("model_capability", "basic")
if CapabilityTier(cap) in (CapabilityTier.STANDARD, CapabilityTier.ADVANCED):
    # Rich structured analysis
else:
    # Simpler binary signal
```

### Key conventions

- **Never raise from `detect()`** — wrap in `try/except`, return `[]
- **Every finding needs evidence** — never return a Finding without at least one Evidence item
- **Return `[]` when the detector doesn't apply** (wrong language, tool missing, no relevant files)
- **Catch `FileNotFoundError`** for external tools and log at `warning` level
- **Use `COMMON_SKIP_DIRS`** from `base.py` to skip `node_modules`, `.venv`, `__pycache__`, etc.
- **Fingerprints are assigned by the pipeline** — detectors never set `fingerprint` on Findings
- **Log at `info` level** for normal operation (`logger.info("my-detector found %d issues", len(findings))`)

### External plugin (pip-installable)

Third-party detectors can be installed without modifying Sentinel itself. Create a Python package with this `pyproject.toml`:

```toml
[project]
name = "sentinel-detector-xyz"
version = "0.1.0"
dependencies = ["local-repo-sentinel>=0.1.0"]

[project.entry-points."sentinel.detectors"]
xyz = "sentinel_detector_xyz.detector"  # module containing your Detector subclass
```

After `pip install sentinel-detector-xyz`, the detector is auto-discovered on the next scan. No Sentinel config changes needed. If the detector name collides with a built-in, the built-in wins (with a warning logged).

See [ADR-012](docs/architecture/decisions/012-entry-points-plugin-system.md) for the design rationale.

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
