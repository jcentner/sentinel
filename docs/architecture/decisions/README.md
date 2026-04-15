# Architecture Decision Records

This directory tracks significant architecture and design decisions for Local Repo Sentinel.

## Format

We use a lightweight ADR format based on [MADR](https://adr.github.io/madr/):

```markdown
# ADR-NNN: Title

**Status**: Proposed | Accepted | Deprecated | Superseded by ADR-NNN
**Date**: YYYY-MM-DD
**Deciders**: Who was involved

## Context
What is the issue we're facing? What forces are at play?

## Decision
What did we decide to do?

## Consequences
What are the positive, negative, and neutral consequences?

## Alternatives considered
What other options were evaluated and why were they rejected?
```

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](001-local-first-execution.md) | Local-first execution model | Accepted | 2026-03-28 |
| [002](002-deterministic-detectors-first.md) | Deterministic detectors as primary signal source | Accepted | 2026-03-28 |
| [003](003-model-agnostic-via-ollama.md) | Model-agnostic design via Ollama | Superseded by ADR-010 | 2026-03-28 |
| [004](004-sqlite-state-from-day-one.md) | SQLite persistent state from day one | Accepted | 2026-03-28 |
| [005](005-docs-drift-first-class-detector.md) | Docs-drift as a first-class detector category | Accepted | 2026-03-28 |
| [006](006-copilot-agent-primary-dev-tool.md) | GitHub Copilot agent mode as primary development tool | Accepted | 2026-03-28 |
| [007](007-python-implementation-language.md) | Python as implementation language | Accepted | 2026-04-03 |
| [008](008-evaluation-criteria.md) | Evaluation criteria defined before implementation | Accepted | 2026-04-04 |
| [009](009-embedding-context-gatherer.md) | Embedding-based context gatherer | Accepted | 2026-04-05 |
| [010](010-pluggable-model-provider.md) | Pluggable model provider interface | Accepted | 2026-04-07 |
| [011](011-capability-tier-system.md) | Capability tier system for detectors | Superseded by ADR-016 | 2026-04-08 |
| [012](012-entry-points-plugin-system.md) | Entry-points plugin system for third-party detectors | Accepted | 2026-04-08 |
| [013](013-per-detector-model-providers.md) | Per-detector model providers | Accepted | 2026-04-09 |
| [014](014-replay-based-eval.md) | Replay-based eval for judge and synthesis paths | Accepted | 2026-04-10 |
| [016](016-benchmark-driven-model-quality.md) | Benchmark-driven model quality (supersedes ADR-011) | Accepted | 2026-04-12 |
| [017](017-async-model-provider.md) | Async model provider with backward-compatible concurrency | Accepted | 2026-04-13 |
| [018](018-benchmark-rigor.md) | Benchmark rigor as core engineering discipline | Accepted | 2026-04-14 |

## Creating a new ADR

1. Copy the template above
2. Number sequentially (next: 019)
3. Create `NNN-short-kebab-title.md`
4. Add to the index table above
5. Record the decision in the commit that implements it where possible
