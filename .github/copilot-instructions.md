# Sentinel — Copilot Instructions

You are working on **Local Repo Sentinel**, a local evidence-backed repository issue triage system for overnight code health monitoring.

## Project Context

- **What it does**: Scans repos on a schedule, runs deterministic detectors + LLM judgment, produces a morning report of findings, creates GitHub issues after human approval.
- **What it does NOT do**: Implement fixes, make architecture plans, open PRs, act autonomously.
- **Target environment**: Windows 11 + WSL 2 Ubuntu, 8 GB VRAM GPUs, Ollama for local models (default provider).
- **Implementation language**: Python (see ADR-007).
- **Primary LLM**: Qwen3.5 4B via Ollama (default provider — design is provider-agnostic, see ADR-010).

## Key Architecture Decisions

Before making design choices, check existing [ADRs](docs/architecture/decisions/). Key decisions already made:
- ADR-001: Local-first execution (no cloud API calls except optional GitHub issue creation and opt-in cloud model providers)
- ADR-002: Deterministic detectors as primary signal, LLM as judgment layer
- ADR-003: Model-agnostic via Ollama (superseded by ADR-010)
- ADR-004: SQLite persistent state from day one
- ADR-005: Docs-drift as a first-class detector category
- ADR-006: GitHub Copilot agent mode as primary dev tool
- ADR-007: Python as implementation language
- ADR-008: Evaluation criteria defined before implementation
- ADR-009: Embedding-based context gatherer
- ADR-010: Pluggable model provider interface (Ollama default, OpenAI-compatible supported)
- ADR-011: Capability tier system for detectors
- ADR-012: Entry-points plugin system for third-party detectors
- ADR-013: Per-detector model providers
- ADR-014: Replay-based eval for judge and synthesis paths

## Documentation

- Vision lock: [docs/vision/VISION-LOCK.md](docs/vision/VISION-LOCK.md)
- Strategy: [docs/vision/strategy.md](docs/vision/strategy.md)
- Architecture: [docs/architecture/overview.md](docs/architecture/overview.md)
- Detector design: [docs/architecture/detector-interface.md](docs/architecture/detector-interface.md)
- Compatibility matrix: [docs/reference/compatibility-matrix.md](docs/reference/compatibility-matrix.md)
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
- **Model-detector compatibility must be transparent.** Different detectors have different model quality requirements. The compatibility matrix (`docs/reference/compatibility-matrix.md`) and web UI must show empirical quality ratings. When a model-detector combination has a known poor rating (e.g., test-coherence + 4B at ~40% FP), the system must warn the user — not silently produce noisy results. Trust requires transparency.
- **Capability tiers are empirical, not assumed.** Tier-to-model mapping is based on measured benchmark quality, not parameter count. 9B local maps to basic (not standard) because it's in the same empirical class as 4B for Sentinel's tasks. The standard tier boundary is the quality jump at cloud-nano. Never equate models based on size alone — always cite benchmark evidence.
