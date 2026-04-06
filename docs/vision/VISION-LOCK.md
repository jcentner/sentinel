# Vision Lock — Local Repo Sentinel

> **Version**: 2.2
> **Updated**: 2026-04-06
> **Supersedes**: [archive/VISION-LOCK-v1.md](archive/VISION-LOCK-v1.md) + VISION-REVISION-001 through 005
> **Status**: Active baseline. Substantive changes require a new version with a changelog entry appended to this file.

## Problem Statement

Developer-facing AI tools focus on helping in the moment — autocomplete, chat, inline edits. There is no tool that works in the background, revisits a repository with fresh context overnight, and surfaces overlooked issues for human review in the morning. Existing adjacent tools are either PR-scoped reviewers (triggered per diff, not persistent), autonomous agents (implement fixes and open PRs), or static analyzers (powerful but not cross-artifact, not persistent, not summarized).

## Target User

A developer on Windows 11 + WSL 2 Ubuntu with 8 GB VRAM GPUs, comfortable running local models via Ollama, working across multiple projects including a primary role and consulting/client engagements. Privacy matters — client code must never leave the machine.

## Core Concept

Local Repo Sentinel is a local, evidence-backed repository issue triage system for overnight code health monitoring. It runs deterministic and heuristic detectors to produce candidate findings, gathers contextual evidence via embeddings, and uses a small local LLM as a judgment and summarization layer. It produces a concise morning report of findings worth human attention. After explicit approval, it can create GitHub issues from selected findings. A browser-based web UI provides the full triage workflow alongside the CLI.

## Explicit Non-Goals

1. **Not a code fixer**: Does not implement fixes, suggest patches, or plan refactors.
2. **Not an architect**: Does not make architecture decisions for the user.
3. **Not autonomous**: Does not take external actions without explicit human approval.
4. **Not a PR reviewer**: Not triggered per-PR or per-diff (though it may run incrementally on changed files).
5. **Not a Copilot replacement**: Complements interactive coding tools; does not compete with them.
6. **Not a cloud service**: All processing is local except the optional GitHub issue creation API call.
7. **Not a CI/CD gate**: It is a background advisor, not a blocker.

## Product Constraints

| Constraint | Description |
|-----------|-------------|
| Human approval gate | No external action (GitHub issue creation) without explicit human approval |
| Morning report scannability | Report must be scannable in under 2 minutes |
| Evidence-backed findings | Every finding must cite concrete evidence — code, docs, lint output, git history |
| Precision over breadth | 3 real issues beats 20 noisy ones. False positive rate is the hardest problem. |
| Deduplication | State store tracks fingerprinted findings to avoid repeat noise across runs |
| Dual interface | CLI for scripting and AI agent integration; web UI for human triage. Feature parity between them. |
| Modular by default | Users install only the dependencies their projects need. Developers and agents can add detectors, language support, or integrations independently without touching core code. |

## Technical Constraints

| Constraint | Description |
|-----------|-------------|
| Local-first execution | All inference, embedding, state storage, and report generation on the user's machine |
| 8 GB VRAM budget | Models must fit ~4B parameters at Q4_K_M quantization |
| Ollama as model interface | All model interaction through Ollama API; model names are config, not code |
| Model-agnostic prompts | Prompts target general instruction-following, not model-specific features |
| SQLite state store | Persistent state; embedded, zero-deployment, single-file |
| Python implementation | Chosen for ML/NLP ecosystem, tree-sitter bindings, native sqlite3 |
| Deterministic-first signals | Linters and heuristics are primary; LLM is judgment layer, not signal source |
| No JS build step | Web UI uses server-rendered templates with progressive enhancement (htmx). No Node/npm. |
| Modular dependencies | Optional dependency groups (`[web]`, `[detectors]`, language-specific linters). Core pipeline has minimal required deps. |

## Pipeline

```
detect → fingerprint → deduplicate → gather context → judge → store → report
```

Deduplication happens before the expensive steps (context gathering, LLM judgment) so only novel, non-suppressed findings consume compute.

## What Exists Today

### Core Pipeline
- **9 pluggable detectors** covering Python (ruff, pip-audit, complexity), JS/TS (ESLint/Biome), Go (golangci-lint), Rust (cargo clippy), dependency auditing, docs-drift, git churn hotspots, and TODO/FIXME scanning
- **Custom detector loading**: external detectors via `detectors_dir` config, auto-registered through `__init_subclass__`
- **Embedding-based context gathering**: opt-in via Ollama, falls back to file-proximity heuristics
- **LLM judge**: structured judgment via Ollama. System degrades gracefully (raw findings only) when no model is running
- **Finding fingerprinting**: content-hash deduplication, suppression persistence, occurrence tracking
- **Two-pass clustering**: pattern clustering (same detector + normalized title) then directory clustering (3+ findings in shared parent)
- **Morning report**: markdown output, severity-grouped, clustered, with occurrence badges

### CLI
14 commands: `scan`, `scan-all`, `init`, `doctor`, `show`, `suppress`, `approve`, `create-issues`, `history`, `eval`, `eval-history`, `index`, `serve`, plus global `--version`/`-v`/`-q`. All key commands support `--json-output` for AI agent integration.

### Web UI (`sentinel serve`)
Browser-based triage interface with run review, finding detail, bulk actions, GitHub issue creation, scan configuration, evaluation with trend chart, and run comparison. Dark/light themes.

### GitHub Integration
Issue creation from approved findings with fingerprint-based dedup. Environment variable config (no secrets in config files).

### Multi-repo
`scan-all` scans multiple repos into a shared database. Web UI and CLI display runs across all repos.

### Quality Infrastructure
CI pipeline (GitHub Actions, Python 3.11–3.13, ruff, mypy strict, pytest with coverage). 614 tests, 90% code coverage. Output samples, CONTRIBUTING.md, TOML config scaffolding via `init`.

## Success Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Install, point at repo, get useful morning report | **Met** |
| 2 | Report scannable in < 2 minutes | **Met** |
| 3 | Majority of findings are real or worth reviewing | **Met** |
| 4 | Findings deduplicated across runs | **Met** |
| 5 | Works fully offline except optional GitHub | **Met** |
| 6 | Swap LLM model via config, not code | **Met** |
| 7 | Suppress a FP and it stays suppressed | **Met** |
| 8 | Full triage cycle from the browser without CLI | **Met** |
| 9 | CLI usable by AI agents (JSON output, exit codes) | **Met** |

## Evaluation Criteria

| Metric | Target |
|--------|--------|
| Precision@k | ≥ 70% |
| False positive rate | < 30% per run |
| Review time | < 2 minutes |
| Findings → issues rate | Track only |
| Detector coverage | ≥ 3 categories |
| Repeatability | 100% for deterministic |

## Architecture Invariants

These hold across all versions and must not be violated:

1. **Detectors are pluggable**: every detector produces `Finding` objects through the same interface. Adding a detector never requires changing the pipeline. Custom detectors can be loaded from an external directory.
2. **LLM is replaceable**: changing the model is a config change. The pipeline works without any model running.
3. **State is persistent**: every run reads from and writes to the SQLite state store.
4. **Evidence is mandatory**: a finding without evidence is invalid.
5. **Human approval gates external actions**: no GitHub API calls without explicit user confirmation.
6. **Single repo per run**: each run targets one repository.
7. **Parallel extensibility**: new detectors and language integrations are isolated modules. Multiple developers or agents can work on different language support packages simultaneously without merge conflicts in core code.

## Where We're Going

These are the next areas of investment, roughly priority-ordered. Each will be planned and validated before implementation.

### Multi-language repo support — Shipped
Detectors now cover Python (ruff, pip-audit, AST complexity), JS/TS (eslint-runner wrapping ESLint/Biome), Go (golangci-lint), and Rust (cargo clippy). Language-neutral detectors (todo-scanner, docs-drift, git-hotspots) work across all languages. Each language linter is an isolated detector module. *Remaining*: real-world validation on non-Python repos, optional language-specific pip extras.

### Multi-repo support — Shipped
`sentinel scan-all REPO1 REPO2 ... --db shared.db` scans multiple repos into a shared database. Web UI and `sentinel history` display runs across all repos. Partial failure handling (exit code 2). See OQ-005 resolution.

### Root-cause finding grouping — Shipped
Two-pass clustering: pattern clustering (same detector + normalized title across directories) applied first, then directory clustering (3+ findings sharing a parent directory). Both the markdown report and web UI display clustered findings.

### CLI as an AI-agent interface — Shipped
All key commands support `--json-output`. `-q/--quiet` mode for scripts. Predictable exit codes. `suppress` and `approve` support `--json-output`. `sentinel doctor --json-output` for dependency checking.

### Eval metrics dashboard — Shipped
Eval results persist in SQLite via `eval_store`. Web UI includes a server-side SVG trend chart showing precision/recall over time. `sentinel eval-history` lists past eval runs.

### Model benchmarking
Compare model sizes and quantization levels (qwen3.5 4B vs 9B, Q4 vs Q6) to find the quality/VRAM sweet spot. Document context length requirements empirically. *Requires Ollama with multiple models pulled.*

### Packaging and distribution — Mostly shipped
CI/CD pipeline (GitHub Actions, Python 3.11–3.13 matrix, ruff + mypy + pytest with coverage). Output samples in repo. CONTRIBUTING.md. PyPI-ready wheel with templates/static included. *Remaining*: `pip install local-repo-sentinel` from PyPI (needs credentials/trusted publisher).

## Out of Scope (permanent)

These are explicitly excluded from the project's vision, not deferred:

- Implementing code fixes or generating patches
- Making architecture recommendations
- Opening pull requests
- Cloud-hosted execution
- Real-time / in-editor integration
- Built-in scheduling (use system cron/systemd timers)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| FP rate too high with 4B model | Medium | High | Deterministic-first architecture; LLM is judgment layer; suppression mechanism |
| Single-language limitation reduces real-world value | Medium | Medium | Prioritize multi-language detector support |
| Fingerprinting breaks on file renames | Medium | Low | Accept; add similar-finding heuristic later |
| Ollama dependency creates friction | Low | Low | Degrade gracefully; document setup clearly |

## Changelog

### v2.2 (2026-04-06)
- "What Exists Today" expanded: 9 detectors (Go, Rust added), 14 CLI commands, multi-repo, clustering, quality infrastructure
- "Where We're Going" items marked shipped: multi-language, multi-repo, root-cause grouping, CLI agent interface, eval dashboard, packaging (mostly)
- Remaining future items: model benchmarking, PyPI publish

### v2.1 (2026-04-06)
- Added eslint-runner detector for JS/TS linting via ESLint or Biome (multi-language support foundation)
- Added `--json-output` flag for machine-readable CLI output
- Success criterion #9 added: CLI usable by AI agents

### v2.0 (2026-04-06)
Consolidated from VISION-LOCK v1.0 + VISION-REVISION-001 through 005. Key changes from v1.0:
- Pipeline order updated (dedup before context/judge — VR-001)
- Web UI added as a core delivery surface, not just a future item (VR-002, VR-004, VR-005)
- Embedding-based context gathering moved from "not in MVP" to shipped (VR-003)
- Built-in scheduling explicitly moved to "out of scope" (VR-004/TD-009)
- "What Exists Today" and "Where We're Going" sections added
- Implementation-level content removed (belongs in architecture docs, not vision)
- Stale unresolved assumptions removed (validated by implementation experience)

### v1.0 (2026-04-04)
Initial baseline synthesized from repository docs. See [archive/VISION-LOCK-v1.md](archive/VISION-LOCK-v1.md).
