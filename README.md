# Local Repo Sentinel

**A local, evidence-backed repository issue triage system for overnight code health monitoring.**

Repo Sentinel runs on a local development machine, watches a codebase over time, collects evidence from the repo and its surrounding artifacts, and produces a concise morning report of likely issues worth a human reviewing. After approval, it turns selected findings into GitHub issues.

## What it does

- Scans one or more repos on a schedule (nightly, on-demand, or triggered by git activity)
- Runs deterministic detectors (linters, tests, dependency audits, docs-drift checks)
- Gathers supporting context via embeddings + reranking
- Uses a small local LLM as a judgment/summarization layer
- Clusters and deduplicates findings across runs
- Drafts a morning report organized by severity and confidence
- Creates GitHub issues from approved findings

## What it explicitly does not do

- Implement fixes
- Make architecture plans
- Open pull requests
- Act autonomously on code

## Why local

Running locally supports privacy, low marginal cost, offline iteration, and a workflow that fits naturally into personal and client repositories. It shows what a small local model can do when paired with a well-bounded problem, repeated runs, and strong evidence gathering.

## Status

**Pre-development** — Establishing project vision, architecture decisions, and development workflow. See [docs/vision/](docs/vision/) for strategy and [docs/architecture/](docs/architecture/) for technical design.

## Documentation

| Area | Location | Purpose |
|------|----------|---------|
| Vision & Strategy | [docs/vision/](docs/vision/) | High-level goals, positioning, what we're building and why |
| Architecture | [docs/architecture/](docs/architecture/) | Technical design, detector interface, system overview |
| Architecture Decisions | [docs/architecture/decisions/](docs/architecture/decisions/) | ADRs — recorded design choices with context and rationale |
| Reference | [docs/reference/](docs/reference/) | Open questions, tech debt tracker, glossary |
| Analysis | [docs/analysis/](docs/analysis/) | Competitive landscape, critical review of the design |
| Roadmap | [roadmap/](roadmap/) | Phased development plan |
| Dev Workflow | [.github/prompts/PROMPT-GUIDE.md](.github/prompts/PROMPT-GUIDE.md) | Copilot prompt dev cycle and usage guide |

## Development

This repo is primarily developed using GitHub Copilot in agent mode (Claude Opus 4.6). The development workflow is codified as reusable prompt files — see the [Prompt Guide](.github/prompts/PROMPT-GUIDE.md) for the full dev cycle.

## License

TBD
