# Competitive Landscape

> Last updated: 2026-04-10. This space moves fast — revisit quarterly.

## The core problem nobody else solves

The faster you build with AI, the faster things drift.

AI coding tools help you write code faster, but they don't help you notice when your docs, tests, and code start disagreeing with each other. Existing tools fall into categories that each miss this:

- **Linters** check code quality within a single file. They don't check if your README still describes reality.
- **PR reviewers** are triggered per-diff. They don't revisit the repo with fresh context after a week of rapid changes.
- **Autonomous agents** implement fixes and open PRs. They don't observe and report — they act.
- **CI/CD gates** block deploys. They don't surface the slow-burn drift that accumulates between deploys.

The hardest problems to catch during fast development — especially AI-assisted development — are **cross-artifact inconsistencies**: drift between code, docs, tests, config, and dependencies that accumulates silently and compounds. No single tool owns the whole picture.

## Sentinel's position

Sentinel is a **local, evidence-backed repository health monitor** that combines two things nobody else combines:

1. **Deterministic detectors** (lint, broken links, dead code, complexity, CVEs) — cheap, fast, reliable
2. **LLM-powered cross-artifact analysis** (docs vs code, tests vs implementation) — catches semantic drift that regex can't

Both flow through a shared pipeline: fingerprint → deduplicate → judge → store → report. The LLM is a judgment layer on top of deterministic signals, not a replacement for them.

**Key differentiators:**
- Runs on schedule (overnight), not per-PR
- Local-first on consumer hardware (8 GB VRAM)
- Cross-artifact: compares docs against code, tests against implementation, env configs against usage
- Persistent state with dedup — suppress a false positive once, it stays suppressed
- Human approval gate before any external action (GitHub issues)
- Even a 4B local model can reliably deliver binary triage signals ("this doc section needs review")

## Direct competitors and adjacent tools

### PR-time AI reviewers (triggered by diffs, not standing health)

| Tool | Description | Relevance to Sentinel |
|------|-------------|----------------------|
| **jstar-code-review** | Local-first AI code review with 2-stage triage, documentation drift detection, deterministic security audit | Closest feature overlap (docs-drift tag). But PR-scoped, not persistent |
| **PR-Guardian-AI** | AI-powered PR review via webhooks + FastAPI | Cloud-oriented, PR-scoped |
| **reviewd** | Local AI PR reviewer for GitHub/BitBucket, terminal-based | PR-scoped, uses hosted CLIs |
| **ai-code-gate** | GitHub Actions pipeline for detecting/auditing AI-generated code | CI-scoped, not standing health |

### Overnight execution agents (implement code, not observe)

| Tool | Description | Relevance to Sentinel |
|------|-------------|----------------------|
| **night-watch-cli** | Overnight PRD execution. Runs Claude CLI / Codex in worktrees, opens PRs | Closest "overnight" competitor. But it *writes code*, we *surface issues*. Recently added "create board issues from audit findings" |
| **autonomous-dev-team** | Turns GitHub issues into merged PRs with zero human intervention | Full autonomy — opposite end of the spectrum |

### Static analysis tools (deterministic, no LLM — we consume these)

| Tool | Stars | Description | Use in Sentinel |
|------|-------|-------------|-----------------|
| **SQLFluff** | 9.6k | SQL linter, multi-dialect, extensible rules, Python API | Detector: SQL anti-patterns |
| **Semgrep** | 11k+ | Multi-language pattern-based static analysis | Detector: security, code quality |
| **ast-grep** | 8k+ | Structural code search/lint via tree-sitter | Detector: custom patterns |
| **ruff** | 35k+ | Python linter/formatter (Rust) | Detector: Python code quality |
| **ESLint** | 25k+ | JavaScript/TypeScript linter | Detector: TS/JS code quality |
| **ShellCheck** | 36k+ | Shell script analysis | Detector: shell scripts |

### Documentation testing tools

| Tool | Description | Relevance to Sentinel |
|------|-------------|----------------------|
| **mdproof** | Turn markdown docs into executable tests | Narrow overlap on docs verification |
| **zero-context-validation** | Claude skill for testing doc completeness via blind sub-agents | Concept overlap |
| **markdown-clitest** | Test CLI commands and examples in markdown docs | Could inform docs-drift extraction |

## Where Sentinel sits (the gap)

No existing tool combines all of:

1. **Scheduled/overnight runs** (not PR-triggered)
2. **Deterministic detectors + LLM judgment layer**
3. **Cross-artifact consistency checking** (code ↔ docs ↔ tests ↔ config)
4. **Persistent state** for dedup and false-positive suppression
5. **Human approval gate** before any external action
6. **Fully local execution** on consumer hardware (8 GB VRAM)
7. **AI-agent integration** (JSON output, exit codes, `.skill` for Copilot setup)

Night-watch-cli is the nearest in the "overnight" space, but it fundamentally executes work (opens PRs). Sentinel fundamentally observes and reports.

### The "observed" differentiator

From real-world validation (104 findings from a production Next.js + Python project, 88% confirmation rate):

- **Docs-drift broken links**: 100% accuracy across 56 findings — every stale path reference was genuinely broken/missing (manually verified).
- **Semantic drift**: Even a 4B model can reliably answer "does this doc section match this code?" as a binary signal.
- **LLM fabrication risk**: The LLM judge confirmed 42 out of 42 obvious non-path patterns (dates, CSS values) as missing files, each with plausible reasoning. This is why deterministic detectors come first and the LLM is a judgment layer, not the primary signal.

*Note: The 88% confirmation rate is the LLM judge's confirmation rate — the judge agreed that 92/104 post-dedup findings were worth reviewing. The docs-drift accuracy was independently verified by manual inspection. See [benchmarks/](../../benchmarks/) for raw data.*

The cross-artifact detectors — docs-drift, semantic-drift, test-coherence, stale-env, unused-deps, dead-code — find things that hide in plain sight because no single tool owns the whole picture. They compound as projects grow, quietly confusing every agent and human who touches the codebase.

## Tools to consume as detectors

These are not competitors — they're upstream tools we wrap:
- ESLint, ruff, SQLFluff, Semgrep, ast-grep, ShellCheck
- npm audit, pip-audit
- Git (history, blame, log)
- tree-sitter (AST extraction)
