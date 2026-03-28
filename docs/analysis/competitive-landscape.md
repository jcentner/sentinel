# Competitive Landscape

> Researched 2026-03-28. This space moves fast — revisit quarterly.

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

Night-watch-cli is the nearest in the "overnight" space, but it fundamentally executes work (opens PRs). Sentinel fundamentally observes and reports.

## Tools to consume as detectors

These are not competitors — they're upstream tools we wrap:
- ESLint, ruff, SQLFluff, Semgrep, ast-grep, ShellCheck
- npm audit, pip-audit
- Git (history, blame, log)
- tree-sitter (AST extraction)
