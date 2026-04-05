# Local Repo Sentinel

**A local, evidence-backed repository issue triage system for overnight code health monitoring.**

Sentinel runs on your local machine, scans a codebase with deterministic detectors and an optional LLM judgment layer, deduplicates findings across runs, and produces a concise morning report of issues worth reviewing. After explicit approval, selected findings can become GitHub issues.

## What it does

- Runs 5 detectors: TODO/FIXME scanner, linter (ruff), dependency audit (pip-audit), docs-drift checker, git churn hotspots
- Gathers contextual evidence per finding (surrounding code, git history, related tests)
- Uses a local LLM via Ollama as a judgment/summarization layer (optional — degrades gracefully)
- Fingerprints and deduplicates findings across runs via SQLite
- Tracks finding persistence across runs (recurring findings get higher visibility)
- Produces a scannable markdown morning report grouped by severity
- Supports suppressing false positives and approving findings for GitHub issue creation
- Creates GitHub issues from approved findings (with deduplication and dry-run mode)

## What it explicitly does not do

- Implement fixes
- Make architecture plans
- Open pull requests
- Act autonomously on code

## Why local

Running locally supports privacy, low marginal cost, offline iteration, and a workflow that fits naturally into personal and client repositories. Client code never leaves your machine.

## Status

**All MVP success criteria met.** 5 detectors, LLM judge, docs-drift detection, finding persistence, git churn hotspots, and GitHub issue creation. 252 tests, real-world validated. See the [roadmap](roadmap/) for details.

## Quick Start

### Prerequisites

- Python 3.11+
- Git
- [Ollama](https://ollama.com/) (optional, for LLM judgment layer)

### Installation

```bash
git clone <repo-url> && cd sentinel
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[detectors]"
```

The `[detectors]` extra installs ruff and pip-audit for full detector coverage.

### Usage

**Scan a repository:**

```bash
sentinel scan /path/to/repo
```

This produces a markdown report at `/path/to/repo/.sentinel/report.md`.

**Scan without the LLM judge** (if Ollama is not running):

```bash
sentinel scan /path/to/repo --skip-judge
```

**Incremental scan** (only files with committed changes since the last run):

```bash
sentinel scan /path/to/repo --incremental
```

**Suppress a false positive:**

```bash
sentinel suppress <finding-id>
```

**Approve a finding for issue creation:**

```bash
sentinel approve <finding-id>
```

**View scan history:**

```bash
sentinel history
```

### Options

| Option | Description |
|--------|-------------|
| `--model TEXT` | Ollama model name (default: `qwen3.5:4b`) |
| `--ollama-url TEXT` | Ollama API URL (default: `http://localhost:11434`) |
| `-o, --output TEXT` | Custom report output path |
| `--skip-judge` | Skip LLM judge, use raw detector findings |
| `--incremental` | Only scan files changed since the last completed run |
| `--db TEXT` | Custom database path |
| `-v, --verbose` | Enable verbose logging |

**Evaluate detector accuracy against ground truth:**

```bash
sentinel eval /path/to/repo
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

### Configuration

Create a `sentinel.toml` in your repo root to customize behavior:

```toml
[sentinel]
model = "qwen3.5:4b"          # Ollama model name
ollama_url = "http://localhost:11434"
skip_judge = false             # true to skip LLM judgment
db_path = ".sentinel/sentinel.db"
output_dir = ".sentinel"
```

### Development

```bash
pip install -e ".[dev]"
pytest                  # run tests
ruff check src/ tests/  # lint
```

## Documentation

| Area | Location | Purpose |
|------|----------|---------|
| Vision & Strategy | [docs/vision/](docs/vision/) | High-level goals, positioning, what we're building and why |
| Architecture | [docs/architecture/](docs/architecture/) | Technical design, detector interface, system overview |
| Architecture Decisions | [docs/architecture/decisions/](docs/architecture/decisions/) | ADRs — recorded design choices with context and rationale |
| Reference | [docs/reference/](docs/reference/) | Open questions, tech debt tracker, glossary |
| Analysis | [docs/analysis/](docs/analysis/) | Competitive landscape, critical review of the design |
| Roadmap | [roadmap/](roadmap/) | Phased development plan |

## License

MIT
