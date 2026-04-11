# Local Repo Sentinel

**A local, evidence-backed repository issue triage system for overnight code health monitoring.**

📖 **[Documentation Wiki](https://github.com/jcentner/sentinel/wiki)** — Installation, configuration, detector reference, and more.

Sentinel runs on your local machine, scans a codebase with deterministic detectors and an optional LLM judgment layer, deduplicates findings across runs, and produces a concise morning report of issues worth reviewing. After explicit approval, selected findings can become GitHub issues.

## What it does

- Runs **14 detectors**: TODO/FIXME scanner, Python linter (ruff), JS/TS linter (ESLint/Biome), Go linter (golangci-lint), Rust linter (cargo clippy), dependency audit (pip-audit), docs-drift checker, semantic docs-drift (LLM prose vs code comparison), git churn hotspots, cyclomatic complexity, test-code coherence (LLM), stale env config drift, unused dependency detection, dead code / unused exports
- Gathers contextual evidence per finding (surrounding code, git history, related tests, semantic code search via embeddings)
- Uses a pluggable LLM provider as a judgment/summarization layer (Ollama local, Azure, OpenAI-compatible — optional, degrades gracefully)
- Fingerprints and deduplicates findings across runs via SQLite
- Tracks finding persistence across runs (recurring findings get higher visibility)
- Produces a scannable markdown morning report grouped by severity
- Clusters related findings by root-cause pattern and directory to reduce noise
- **Finding cluster synthesis**: LLM-powered root-cause analysis collapses related findings into actionable items (standard+ capability)
- Supports suppressing false positives and approving findings for GitHub issue creation
- Creates GitHub issues from approved findings (with deduplication and dry-run mode)
- **Detector configurability**: enable/disable detectors via config, CLI (`--detectors`, `--skip-detectors`), or web UI
- **Plugin system**: third-party detectors installable via `pip install` (entry-points discovery, ADR-012)
- **Capability-tiered detectors**: detectors declare minimum model requirements; richer analysis with more powerful models
- **Setup flow**: `sentinel init --profile minimal|standard|full` guides detector and model selection

## What it explicitly does not do

- Implement fixes
- Make architecture plans
- Open pull requests
- Act autonomously on code

## Why local

Running locally supports privacy, low marginal cost, offline iteration, and a workflow that fits naturally into personal and client repositories. Client code never leaves your machine.

## Status

**All MVP success criteria met.** 14 detectors (Python, JS/TS, Go, Rust, deps, docs, semantic-drift, test-coherence, git, complexity, dead-code, stale-env, unused-deps) with pluggable model providers (Ollama, OpenAI-compatible, Azure), capability-tiered enhanced analysis, finding cluster synthesis, entry-points plugin system, detector configurability, LLM judge, finding persistence, embedding-based semantic context, GitHub issue creation, web UI triage dashboard, multi-repo scanning, full-pipeline eval with replay, and `--json-output` for machine-readable output. 1013 tests. See the [roadmap](roadmap/) for details.

## Quick Start

### Prerequisites

- Python 3.11+
- Git
- [Ollama](https://ollama.com/) (optional — for local LLM judgment; Azure/OpenAI providers also supported)

### Installation

**From PyPI:**

```bash
pip install local-repo-sentinel
# Or with all detector tools (ruff, pip-audit):
pip install "local-repo-sentinel[detectors]"
```

**From source (for development):**

```bash
git clone https://github.com/jcentner/sentinel.git && cd sentinel
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[detectors]"
```

The `[detectors]` extra installs ruff and pip-audit for full detector coverage.

### Usage

**Initialize a new repo for Sentinel:**

```bash
sentinel init /path/to/repo                    # all detectors, basic capability
sentinel init /path/to/repo --profile minimal  # heuristic-only, no LLM needed
sentinel init /path/to/repo --profile full     # all detectors, enhanced analysis
sentinel init /path/to/repo --list-detectors   # show available detectors
```

This creates a `sentinel.toml` with documented defaults, a `.sentinel/` directory, and adds it to `.gitignore`.

**Scan a repository:**

```bash
sentinel scan /path/to/repo
```

This produces a markdown report at `/path/to/repo/.sentinel/report-<run-id>.md`.

**Scan without the LLM judge** (if Ollama is not running):

```bash
sentinel scan /path/to/repo --skip-judge
```

**Incremental scan** (only files with committed changes since the last run):

```bash
sentinel scan /path/to/repo --incremental
```

**Scan with semantic context** (requires an Ollama embedding model):

```bash
sentinel scan /path/to/repo --embed-model nomic-embed-text
```

**Targeted scan** (specific files or directories only):

```bash
sentinel scan /path/to/repo --target src/auth --target src/api/routes.py
```

**Scan multiple repos into a shared database:**

```bash
sentinel scan-all ~/project-a ~/project-b ~/project-c --db ~/.sentinel/all.db --skip-judge
```

All repos go into one database. Use `sentinel serve` with `--db` to view them together, or `sentinel history --db` to list all runs across repos.

**Build the embedding index separately** (optional — scan auto-builds when `--embed-model` is used):

```bash
sentinel index /path/to/repo
```

**Suppress a false positive:**

```bash
sentinel suppress <finding-id>
# Or from a different directory:
sentinel suppress <finding-id> --repo /path/to/repo
```

**Approve a finding for issue creation:**

```bash
sentinel approve <finding-id>
# Or from a different directory:
sentinel approve <finding-id> --repo /path/to/repo
```

**View scan history:**

```bash
sentinel history
```

**Inspect a specific finding:**

```bash
sentinel show <finding-id>
```

**Launch the web UI for browser-based review:**

```bash
pip install "local-repo-sentinel[web]"    # one-time: install web dependencies
sentinel serve /path/to/repo               # auto-opens browser
sentinel serve /path/to/repo --port 9000
sentinel serve /path/to/repo --no-open     # headless (for scripts/agents)
```

The web UI runs on `http://127.0.0.1:8888` by default. It provides:
- **Dark/light mode** — "Night Watch" dark-first theme with toggle (persists across sessions)
- **Run dashboard** — severity stat cards, findings grouped by severity, filter by severity/status/detector
- **Bulk triage** — checkboxes on findings with per-severity "select all" toggle; batch approve or suppress from a sticky action bar
- **Finding detail** — full metadata, evidence, inline approve/suppress with optional reason, user notes/annotations
- **GitHub Issues page** — view approved findings, create GitHub issues or dry-run, config status indicator
- **Configurable scan** — form-based scan with repo path, model override, embedding model, skip-judge, incremental
- **Evaluation page** — run detectors against a ground-truth file to measure precision/recall
- **Settings page** — view active configuration, sentinel.toml status, and GitHub env var status
- **Run history** — all past scan runs with finding counts and scope badges
- **Run comparison** — compare two runs to see new, resolved, and persistent findings
- **Eval trend chart** — server-side SVG chart showing precision/recall trends over time

**Check system dependencies:**

```bash
sentinel doctor
sentinel doctor --json-output   # machine-readable
```

### Options

| Option | Description |
|--------|-------------|
| `--model TEXT` | Model name (default: `qwen3.5:4b`) |
| `--provider TEXT` | Model provider: `ollama`, `openai`, or `azure` |
| `--api-base TEXT` | API base URL for openai/azure providers |
| `--ollama-url TEXT` | Ollama API URL (default: `http://localhost:11434`) |
| `-o, --output TEXT` | Custom report output path |
| `--skip-judge` | Skip LLM judge, use raw detector findings |
| `--capability TEXT` | Model capability tier: `none`, `basic`, `standard`, `advanced` |
| `--incremental` | Only scan files changed since the last completed run |
| `--embed-model TEXT` | Embedding model for semantic context (e.g. `nomic-embed-text`) |
| `--target, -t TEXT` | Scan only specific paths (repeatable) |
| `--detectors TEXT` | Comma-separated list of detectors to enable |
| `--skip-detectors TEXT` | Comma-separated list of detectors to skip |
| `-q, --quiet` | Suppress all output except errors |
| `--json-output` | Output results as JSON (machine-readable) |
| `--db TEXT` | Custom database path |

> **Note**: `-v, --verbose` and `-q, --quiet` are global flags placed before the subcommand: `sentinel -v scan /path/to/repo`. They are mutually exclusive.

**Evaluate detector accuracy against ground truth:**

```bash
sentinel eval /path/to/repo
sentinel eval /path/to/repo --ground-truth /path/to/ground-truth.toml
```

**Create GitHub issues from approved findings:**

```bash
# Set credentials
export SENTINEL_GITHUB_OWNER=your-org
export SENTINEL_GITHUB_REPO=your-repo
export SENTINEL_GITHUB_TOKEN=ghp_...

# Preview what would be created
sentinel create-issues --dry-run

# Create issues
sentinel create-issues
```

### Machine-Readable Output

Most commands support `--json-output` for use by AI agents and scripts:

```bash
# JSON scan results (findings + run metadata)
sentinel scan /path/to/repo --skip-judge --json-output

# JSON finding detail
sentinel show 42 --json-output

# JSON run history
sentinel history --json-output

# JSON eval metrics
sentinel eval /path/to/repo --json-output

# JSON issue creation results
sentinel create-issues --dry-run --json-output

# JSON triage actions
sentinel suppress 42 -r "False positive" --json-output
sentinel approve 42 --json-output
```

Exit codes: `0` = success, `1` = error, `2` = partial failure (scan-all).

### Configuration

Create a `sentinel.toml` in your repo root to customize behavior:

```toml
[sentinel]
provider = "ollama"            # "ollama", "openai", or "azure"
model = "qwen3.5:4b"          # Model name
ollama_url = "http://localhost:11434"
skip_judge = false             # true to skip LLM judgment
model_capability = "basic"     # none, basic, standard, advanced
db_path = ".sentinel/sentinel.db"
output_dir = ".sentinel"
embed_model = ""               # Embedding model (e.g. "nomic-embed-text")
detectors_dir = ""             # Custom detector .py files directory
# num_ctx = 2048               # LLM context window size

# For OpenAI-compatible providers (Azure OpenAI, OpenAI, vLLM, LM Studio):
# provider = "openai"
# api_base = "https://api.openai.com"
# api_key_env = "OPENAI_API_KEY"  # env var containing the API key

# Detector selection (optional — defaults to all):
# enabled_detectors = ["todo-scanner", "lint-runner", "docs-drift"]
# disabled_detectors = ["dead-code"]
```

### Custom Detectors

Add your own detectors by creating Python files in a directory and pointing `detectors_dir` at it:

```python
# my_detectors/license_check.py
from sentinel.detectors.base import Detector
from sentinel.models import DetectorContext, DetectorTier, Finding, Severity

class LicenseDetector(Detector):
    @property
    def name(self): return "license-check"
    @property
    def description(self): return "Check for LICENSE file"
    @property
    def tier(self): return DetectorTier.DETERMINISTIC
    @property
    def categories(self): return ["compliance"]

    def detect(self, context):
        from pathlib import Path
        if not (Path(context.repo_root) / "LICENSE").exists():
            return [Finding(
                detector=self.name, category="compliance",
                title="Missing LICENSE file", severity=Severity.MEDIUM,
                confidence=1.0, description="No LICENSE file found in repo root.",
                evidence=[],
            )]
        return []
```

```toml
# sentinel.toml
[sentinel]
detectors_dir = "my_detectors"
```

### Scheduling overnight runs

Sentinel does not include a built-in scheduler. Use your system's scheduling tools to run scans overnight.

**Linux/WSL (cron):**

```bash
# Edit your crontab
crontab -e

# Run a full scan at 2 AM every night
0 2 * * * /path/to/sentinel/.venv/bin/sentinel scan /path/to/repo --skip-judge >> /tmp/sentinel.log 2>&1

# Or with the LLM judge (requires Ollama running)
0 2 * * * /path/to/sentinel/.venv/bin/sentinel scan /path/to/repo >> /tmp/sentinel.log 2>&1
```

**Linux/WSL (systemd timer):**

```bash
# Create ~/.config/systemd/user/sentinel-scan.service
[Unit]
Description=Sentinel overnight scan

[Service]
Type=oneshot
ExecStart=/path/to/sentinel/.venv/bin/sentinel scan /path/to/repo

# Create ~/.config/systemd/user/sentinel-scan.timer
[Unit]
Description=Run Sentinel scan nightly

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable --now sentinel-scan.timer
```

The morning report will be at `/path/to/repo/.sentinel/report-<run-id>.md`.

### Development

```bash
pip install -e ".[dev]"
pytest                         # run tests
ruff check src/ tests/         # lint
mypy src/sentinel/             # type check
```

## Documentation

| Area | Location | Purpose |
|------|----------|---------|
| Vision & Strategy | [docs/vision/](docs/vision/) | High-level goals, positioning, what we're building and why |
| Architecture | [docs/architecture/](docs/architecture/) | Technical design, detector interface, system overview |
| Architecture Decisions | [docs/architecture/decisions/](docs/architecture/decisions/) | ADRs — recorded design choices with context and rationale |
| Reference | [docs/reference/](docs/reference/) | Open questions, tech debt tracker, glossary, [test repos](docs/reference/test-repos.md) |
| Analysis | [docs/analysis/](docs/analysis/) | Competitive landscape, critical review of the design |
| Roadmap | [roadmap/](roadmap/) | Phased development plan |
| AI Setup Skill | [.github/skills/setup-sentinel/](.github/skills/setup-sentinel/) | Copilot skill for AI-assisted setup and configuration |

## AI Agent Integration

Sentinel is designed to be used by AI agents and development tools:

- **`--json-output`** on all CLI commands for machine-readable output
- **Predictable exit codes**: 0 = success, 1 = error, 2 = partial failure
- **Copilot skill**: `.github/skills/setup-sentinel/SKILL.md` provides step-by-step setup instructions that GitHub Copilot (and other AI agents) can follow
- **Quiet mode**: `-q` suppresses all log output for clean piping
- **Config-driven**: `sentinel.toml` is fully declarative — agents can generate it

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, project structure, and conventions.

## License

MIT
