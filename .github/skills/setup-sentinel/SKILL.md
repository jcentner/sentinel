---
name: setup-sentinel
description: 'Install and configure Local Repo Sentinel for code health monitoring. Use when: setting up Sentinel on a project, configuring detectors, choosing model providers, creating sentinel.toml, running first scan, scheduling overnight scans. Keywords: sentinel, code health, docs drift, linting, overnight scan, repo monitor.'
argument-hint: 'Describe the project (language, framework) for tailored detector config'
---

# Set Up Local Repo Sentinel

Set up Sentinel as an overnight code health monitor for any repository. Sentinel scans for cross-artifact drift (docs vs code, tests vs implementation), lint issues, complexity, dead code, and more — then produces a morning report of findings worth reviewing.

## When to Use

- Setting up Sentinel on a new project
- Configuring which detectors to enable
- Choosing a model provider (local Ollama or cloud)
- Scheduling overnight scans
- Troubleshooting `sentinel doctor` output

## Prerequisites

- Python 3.11+
- (Optional) [Ollama](https://ollama.com/) with a model pulled for LLM judgment
- (Optional) Node.js if scanning JS/TS projects with ESLint
- (Optional) Go toolchain if scanning Go projects
- (Optional) Rust toolchain if scanning Rust projects

## Setup Procedure

### 1. Install Sentinel

```bash
# Core only (deterministic detectors, no web UI)
pip install local-repo-sentinel

# With web UI
pip install "local-repo-sentinel[web]"

# With all language-specific detectors
pip install "local-repo-sentinel[detectors]"

# Everything
pip install "local-repo-sentinel[web,detectors]"

# From source (development)
git clone https://github.com/jcentner/sentinel && cd sentinel
pip install -e ".[web,detectors]"
```

### 2. Initialize Configuration

```bash
cd /path/to/your-project
sentinel init
```

Or use profiles for quick setup:

```bash
# Minimal: deterministic-only, no LLM needed
sentinel init --profile minimal

# Standard: all detectors + basic LLM judgment (default)
sentinel init --profile standard

# Full: all detectors + enhanced LLM analysis (needs 9B+ model)
sentinel init --profile full
```

This creates `sentinel.toml` in the project root.

### 3. Configure for the Project

Edit `sentinel.toml` based on the project's language and needs:

**Python project:**
```toml
[sentinel]
enabled_detectors = [
    "lint-runner",      # ruff
    "todo-scanner",
    "docs-drift",       # broken links, stale refs
    "complexity",
    "dep-audit",        # pip-audit for CVEs
    "unused-deps",
    "dead-code",
    "stale-env",
    "semantic-drift",   # LLM: docs vs code comparison
    "test-coherence",   # LLM: test staleness detection
]
```

**JavaScript/TypeScript project:**
```toml
[sentinel]
enabled_detectors = [
    "eslint-runner",
    "todo-scanner",
    "docs-drift",
    "unused-deps",
    "dead-code",
    "semantic-drift",
    "test-coherence",
]
```

**Go project:**
```toml
[sentinel]
enabled_detectors = [
    "go-linter",        # golangci-lint
    "todo-scanner",
    "docs-drift",
    "complexity",
    "semantic-drift",
]
```

**Rust project:**
```toml
[sentinel]
enabled_detectors = [
    "rust-clippy",
    "todo-scanner",
    "docs-drift",
    "semantic-drift",
]
```

### 4. Configure Model Provider (Optional)

Without a model provider, Sentinel runs deterministic detectors only (still useful).

**Local (Ollama — default, private):**
```toml
[sentinel]
provider = "ollama"
model = "qwen3.5:4b"
ollama_url = "http://localhost:11434"
model_capability = "basic"
```

**Cloud (OpenAI-compatible):**
```toml
[sentinel]
provider = "openai"
model = "gpt-4o-mini"
api_base = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model_capability = "standard"
```

**Azure AI Foundry:**
```toml
[sentinel]
provider = "azure"
model = "gpt-4o-mini"
api_base = "https://your-resource.openai.azure.com"
model_capability = "standard"
```

### 5. Verify Setup

```bash
sentinel doctor /path/to/your-project
```

This checks: Python availability, config validity, model connectivity (if configured), and detector dependencies.

### 6. Run First Scan

```bash
# Quick scan without LLM (fast, see raw findings)
sentinel scan /path/to/your-project --skip-judge

# Full scan with LLM judgment
sentinel scan /path/to/your-project

# View results in browser
sentinel serve /path/to/your-project
```

### 7. Schedule Overnight Scans (Optional)

**Linux/macOS (cron):**
```bash
# Edit crontab
crontab -e

# Run at 2 AM daily
0 2 * * * cd /path/to/your-project && sentinel scan . >> /var/log/sentinel.log 2>&1
```

**Windows (Task Scheduler):**
```powershell
# Create a scheduled task via PowerShell
$action = New-ScheduledTaskAction -Execute "wsl" -Argument "cd /path/to/your-project && sentinel scan ."
$trigger = New-ScheduledTaskTrigger -Daily -At "2:00AM"
Register-ScheduledTask -TaskName "Sentinel Scan" -Action $action -Trigger $trigger
```

## Key Concepts

- **Deterministic detectors** (lint, TODO, broken links) run without an LLM — fast and reliable.
- **LLM-powered detectors** (semantic-drift, test-coherence) compare artifacts semantically — need a model provider.
- **The LLM judge** filters and re-prioritizes all findings — skip with `--skip-judge` if no model is available.
- **Findings are deduplicated** across runs via fingerprinting — suppress false positives once and they stay suppressed.
- **GitHub issue creation** requires `SENTINEL_GITHUB_TOKEN`, `SENTINEL_GITHUB_OWNER`, `SENTINEL_GITHUB_REPO` env vars.

## CLI Quick Reference

| Command | Purpose |
|---------|---------|
| `sentinel scan <repo>` | Run detectors and generate report |
| `sentinel scan <repo> --json-output` | Machine-readable JSON output |
| `sentinel serve <repo>` | Web UI for triage |
| `sentinel doctor <repo>` | Verify setup |
| `sentinel init` | Create config file |
| `sentinel show <repo> --run latest` | Show latest run results |
| `sentinel history <repo>` | Show scan history |
| `sentinel approve <repo> <id>` | Approve finding for GitHub issue |
| `sentinel suppress <repo> <id>` | Suppress false positive |
| `sentinel create-issues <repo>` | Create GitHub issues from approved findings |

## Troubleshooting

- **"No findings"**: Check `sentinel doctor` output. Ensure detectors match the project language.
- **Slow scans**: Use `--skip-judge` to skip the LLM step. Use `--target <dir>` to scan specific directories.
- **Too many false positives**: Suppress with `sentinel suppress`, or disable noisy detectors in config.
- **Model errors**: Run `ollama list` to verify the model is pulled. Check `sentinel doctor` for connectivity.
