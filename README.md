# Local Repo Sentinel

**A local, evidence-backed repository issue triage system for overnight code health monitoring.**

📖 **[Documentation Wiki](https://github.com/jcentner/sentinel/wiki)** — Full CLI reference, web UI guide, configuration, scheduling, and more.

Sentinel runs on your local machine, scans a codebase with deterministic detectors and an optional LLM judgment layer, deduplicates findings across runs, and produces a concise morning report of issues worth reviewing.

## What it does

- **18 detectors** — lint (Python/JS/TS/Go/Rust), docs-drift, semantic docs-drift, test-code coherence, inline comment drift, intent comparison, dependency audit, complexity, dead code, git hotspots, TODO scanner, stale env config, unused deps, CI/CD config drift, architecture drift
- **Cross-artifact LLM analysis** — compares docs vs code, tests vs implementation via pluggable model providers (Ollama local, Azure, OpenAI-compatible)
- **Deduplication + persistence** — fingerprints findings across runs, tracks recurrence, suppresses false positives
- **Morning report** — severity-grouped markdown, scannable in under 2 minutes
- **Web UI** — browser-based triage dashboard with dark/light themes, bulk actions, scan config, eval dashboard
- **GitHub integration** — creates issues from approved findings with dry-run mode
- **Plugin system** — third-party detectors via `pip install` (entry-points, ADR-012)
- **Benchmark-driven model quality** — empirical per-model×detector ratings, not assumed tiers (ADR-016)

## What it does not do

Implement fixes, open PRs, act autonomously, or send data to the cloud without explicit opt-in.

## Quick Start

```bash
# Install
pip install repo-sentinel
pip install "repo-sentinel[detectors]"  # includes ruff, pip-audit

# Initialize (creates sentinel.toml)
sentinel init /path/to/repo

# Scan
sentinel scan /path/to/repo

# Scan without LLM (if Ollama isn't running)
sentinel scan /path/to/repo --skip-judge

# Web UI
pip install "repo-sentinel[web]"
sentinel serve /path/to/repo
```

### Prerequisites

- Python 3.11+
- Git
- [Ollama](https://ollama.com/) (optional — for local LLM judgment)

### Key commands

| Command | Description |
|---------|-------------|
| `sentinel scan <repo>` | Full scan with findings report |
| `sentinel scan <repo> --incremental` | Only files changed since last run |
| `sentinel serve <repo>` | Launch web UI for triage |
| `sentinel init <repo>` | Scaffold config + .sentinel/ directory |
| `sentinel doctor` | Check system dependencies |
| `sentinel eval <repo>` | Evaluate detector accuracy vs ground truth |
| `sentinel benchmark <repo>` | Benchmark model quality per detector |
| `sentinel history` | View past scan runs |
| `sentinel compatibility` | Show model-detector quality matrix |
| `sentinel create-issues` | Create GitHub issues from approved findings |

All commands support `--json-output` for machine-readable output. See `sentinel <command> --help` for full options.

### Configuration

Create `sentinel.toml` in your repo root (or use `sentinel init`):

```toml
[sentinel]
provider = "ollama"           # "ollama", "openai", or "azure"
model = "qwen3.5:4b"         # Model name
model_capability = "basic"    # Hint for prompt strategy (ADR-016)

# Route specific detectors to stronger models:
[sentinel.detector_providers.test-coherence]
provider = "openai"
model = "gpt-5.4-nano"
api_base = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
```

See the [wiki](https://github.com/jcentner/sentinel/wiki) for full configuration reference, scheduling setup, custom detectors, and AI agent integration.

## Documentation

| Area | Location |
|------|----------|
| Vision & strategy | [docs/vision/](docs/vision/) |
| Architecture & ADRs | [docs/architecture/](docs/architecture/) |
| Model compatibility | [docs/reference/compatibility-matrix.md](docs/reference/compatibility-matrix.md) |
| Open questions & tech debt | [docs/reference/](docs/reference/) |
| Competitive analysis | [docs/analysis/](docs/analysis/) |
| AI setup skill | [.github/skills/setup-sentinel/](.github/skills/setup-sentinel/) |

## Development

```bash
pip install -e ".[dev]"
pytest                         # 1290 tests
ruff check src/ tests/         # lint
mypy src/sentinel/             # type check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for project structure and conventions.

## License

MIT
