# Sentinel — Copilot Instructions

You are working on **Local Repo Sentinel**, a local evidence-backed repository issue triage system for overnight code health monitoring.

## Project Context

- **What it does**: Scans repos on a schedule, runs deterministic detectors + LLM judgment, produces a morning report of findings, creates GitHub issues after human approval.
- **What it does NOT do**: Implement fixes, make architecture plans, open PRs, act autonomously.
- **Target environment**: Windows 11 + WSL 2 Ubuntu, 8 GB VRAM GPUs, Ollama for local models.
- **Primary LLM**: Qwen3.5 4B via Ollama (but design is model-agnostic — see ADR-003).

## Key Architecture Decisions

Before making design choices, check existing [ADRs](docs/architecture/decisions/). Key decisions already made:
- ADR-001: Local-first execution (no cloud API calls except optional GitHub issue creation)
- ADR-002: Deterministic detectors as primary signal, LLM as judgment layer
- ADR-003: Model-agnostic via Ollama
- ADR-004: SQLite persistent state from day one
- ADR-005: Docs-drift as a first-class detector category
- ADR-006: GitHub Copilot agent mode as primary dev tool

## Documentation

- Vision: [docs/vision/strategy.md](docs/vision/strategy.md)
- Architecture: [docs/architecture/overview.md](docs/architecture/overview.md)
- Detector design: [docs/architecture/detector-interface.md](docs/architecture/detector-interface.md)
- Open questions: [docs/reference/open-questions.md](docs/reference/open-questions.md)
- Tech debt: [docs/reference/tech-debt.md](docs/reference/tech-debt.md)
- Glossary: [docs/reference/glossary.md](docs/reference/glossary.md)

## Coding Conventions

- Check [open questions](docs/reference/open-questions.md) before making decisions that aren't covered by ADRs. If a question is relevant, resolve it and record the decision.
- New significant design choices should be recorded as ADRs in `docs/architecture/decisions/`.
- Use the [tech debt tracker](docs/reference/tech-debt.md) for known compromises.
- When introducing new terms, add them to the [glossary](docs/reference/glossary.md).
- Prefer simple, well-tested code over clever abstractions. This project's credibility depends on precision, not sophistication.
- Every finding the system produces must cite concrete evidence. The same standard applies to the code — every design choice should have a reason.

## Quality Standards

- False positive rate matters more than feature count. A system that surfaces 3 real issues is better than one that surfaces 20 noisy ones.
- The morning report must be scannable in under 2 minutes.
- All external actions (GitHub issue creation) require explicit human approval.
- Test coverage for detectors should include both true positives and known false positive scenarios.
