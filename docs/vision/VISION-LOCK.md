# Vision Lock — Local Repo Sentinel

> **Created**: 2026-04-04
> **Status**: Baseline — append-only after creation. Substantive changes require a VISION-REVISION-NNN.md.

## Problem Statement

Developer-facing AI tools focus on helping in the moment — autocomplete, chat, inline edits. There is no tool that works in the background, revisits a repository with fresh context overnight, and surfaces overlooked issues for human review in the morning. Existing adjacent tools are either PR-scoped reviewers (triggered per diff, not persistent), autonomous agents (implement fixes and open PRs), or static analyzers (powerful but not cross-artifact, not persistent, not summarized).

**Source**: [strategy.md](strategy.md) §"Why this exists"; [positioning.md](positioning.md) §"Positioning gap"; [competitive-landscape.md](../analysis/competitive-landscape.md)

## Target User

A developer on Windows 11 + WSL 2 Ubuntu with 8 GB VRAM GPUs (RTX 3070 Ti / RTX 5070 class), comfortable running local models via Ollama, working across multiple projects including a primary role and consulting/client engagements. Privacy matters — client code must never leave the machine.

**Source**: [strategy.md](strategy.md) §"Target user"; [brainstorm.md](../archive/brainstorm.md) §target user profile

## Core Concept

Local Repo Sentinel is a local, evidence-backed repository issue triage system for overnight code health monitoring. It runs deterministic and heuristic detectors to produce candidate findings, gathers contextual evidence via embeddings, and uses a small local LLM as a judgment and summarization layer. It produces a concise morning report of findings worth human attention. After explicit approval, it can create GitHub issues from selected findings.

**Source**: [strategy.md](strategy.md) §"Core concept"; [positioning.md](positioning.md) §"Core framing"; [overview.md](../architecture/overview.md) §"High-level data flow"

## Explicit Non-Goals

1. **Not a code fixer**: Does not implement fixes, suggest patches, or plan refactors.
2. **Not an architect**: Does not make architecture decisions for the user.
3. **Not autonomous**: Does not take external actions without explicit human approval.
4. **Not a PR reviewer**: Not triggered per-PR or per-diff (though it may run incrementally on changed files).
5. **Not a Copilot replacement**: Complements interactive coding tools; does not compete with them.
6. **Not a cloud service**: All processing is local except the optional GitHub issue creation API call.

**Source**: [strategy.md](strategy.md) §"What it should not pretend to do"; [positioning.md](positioning.md) §"Explicitly not"; [ADR-001](../architecture/decisions/001-local-first-execution.md)

## Product Constraints

| Constraint | Description | Source |
|-----------|-------------|--------|
| Human approval gate | No external action (GitHub issue creation) without explicit human approval | [strategy.md](strategy.md) §"Primary output"; [overview.md](../architecture/overview.md) §"GitHub Issue Creator" |
| Morning report scannability | Report must be scannable in under 2 minutes | [strategy.md](strategy.md) §"Primary output"; [OQ-002](../reference/open-questions.md) |
| Evidence-backed findings | Every finding must cite concrete evidence — code, docs, lint output, git history | [strategy.md](strategy.md) §"What it should be good at"; [detector-interface.md](../architecture/detector-interface.md) §Evidence schema |
| Precision over breadth | 3 real issues beats 20 noisy ones. False positive rate is the hardest problem. | [positioning.md](positioning.md) §"Key warning"; [critical-review.md](../analysis/critical-review.md) §"Honest concerns" |
| Deduplication from day one | State store tracks fingerprinted findings to avoid repeat noise. Dedup is a trust feature. | [ADR-004](../architecture/decisions/004-sqlite-state-from-day-one.md); [overview.md](../architecture/overview.md) §"State Store" |

## Technical Constraints

| Constraint | Description | Source |
|-----------|-------------|--------|
| Local-first execution | All inference, embedding, reranking, state storage, and report generation on the user's machine | [ADR-001](../architecture/decisions/001-local-first-execution.md) |
| 8 GB VRAM budget | Models must fit ~4B parameters at Q4_K_M quantization | [ADR-001](../architecture/decisions/001-local-first-execution.md); [overview.md](../architecture/overview.md) §"What runs where" |
| Ollama as model interface | All model interaction through Ollama API; model names are config, not code | [ADR-003](../architecture/decisions/003-model-agnostic-via-ollama.md) |
| Model-agnostic prompts | Prompts target general instruction-following, not model-specific features | [ADR-003](../architecture/decisions/003-model-agnostic-via-ollama.md) |
| SQLite state store | Persistent state from Phase 1; embedded, zero-deployment, single-file | [ADR-004](../architecture/decisions/004-sqlite-state-from-day-one.md) |
| Python implementation | Chosen for ML/NLP ecosystem, tree-sitter bindings, native sqlite3 | [ADR-007](../architecture/decisions/007-python-implementation-language.md) |
| Deterministic-first signals | Tiers 1+2 (linters, heuristics) are primary; LLM is judgment layer | [ADR-002](../architecture/decisions/002-deterministic-detectors-first.md) |

## Success Criteria

1. A developer can install Sentinel, point it at a local repo, and run a scan that produces a useful morning report.
2. The morning report is scannable in under 2 minutes — one line per finding, expandable evidence, severity tags.
3. False positive rate is subjectively acceptable: the majority of surfaced findings are real or worth reviewing.
4. Findings are deduplicated across runs — the same issue does not appear in consecutive reports.
5. The system works fully offline except for the optional GitHub issue creation step.
6. Swapping the LLM model requires changing configuration, not code.
7. A user can suppress a false positive and it stays suppressed.

**Source**: [strategy.md](strategy.md) §"Primary output", §"Why it is worth building"; [ADR-002](../architecture/decisions/002-deterministic-detectors-first.md); [ADR-003](../architecture/decisions/003-model-agnostic-via-ollama.md); [ADR-004](../architecture/decisions/004-sqlite-state-from-day-one.md); [OQ-007](../reference/open-questions.md)

## Evaluation Criteria

| Metric | Description | Target | Source |
|--------|-------------|--------|--------|
| Precision@k | Of the top-k findings, how many are real? | ≥ 70% for MVP | [OQ-007](../reference/open-questions.md); [critical-review.md](../analysis/critical-review.md) |
| False positive rate | Findings per run that are not real issues | < 30% for MVP | [OQ-007](../reference/open-questions.md) |
| Review time | Time to scan the morning report | < 2 minutes | [strategy.md](strategy.md) §"Primary output" |
| Findings → issues rate | Findings that become legitimate GitHub issues | Track, no target yet | [OQ-007](../reference/open-questions.md) |
| Detector coverage | Categories covered by shipped detectors | ≥ 3 categories for MVP | [detector-interface.md](../architecture/detector-interface.md) §"Planned detectors (MVP)" |
| Repeatability | Same repo state → same findings across runs | 100% for deterministic detectors | [ADR-002](../architecture/decisions/002-deterministic-detectors-first.md) |

## MVP Scope (Phase 1)

The MVP delivers a runnable end-to-end pipeline: trigger → detect → gather context → judge → deduplicate → report.

### In scope

| Component | Description | Source |
|-----------|-------------|--------|
| CLI entry point | `sentinel scan <repo-path>` to trigger a run | [overview.md](../architecture/overview.md) §"Trigger modes"; [OQ-002](../reference/open-questions.md) |
| Detectors: `todo-scanner` | Grep for TODO/FIXME/HACK with age from git blame | [detector-interface.md](../architecture/detector-interface.md) §"Planned detectors (MVP)" |
| Detectors: `lint-runner` | Wrap ruff and normalize output | [detector-interface.md](../architecture/detector-interface.md) §"Planned detectors (MVP)" |
| Detectors: `dep-audit` | Wrap pip-audit | [detector-interface.md](../architecture/detector-interface.md) §"Planned detectors (MVP)" |
| Finding schema | Standardized Finding + Evidence objects | [detector-interface.md](../architecture/detector-interface.md) §"Finding schema" |
| Detector interface | Pluggable detector contract with DetectorContext | [detector-interface.md](../architecture/detector-interface.md) §"Detector contract" |
| Context Gatherer | Retrieve relevant code/docs/history per finding (embeddings optional — may start with simple file-proximity) | [overview.md](../architecture/overview.md) §"Context Gatherer" |
| LLM Judge | Structured judgment via Ollama: is this real, how severe, what evidence? | [overview.md](../architecture/overview.md) §"LLM Judge" |
| SQLite state store | Findings, suppressions, run history, finding lifecycle | [ADR-004](../architecture/decisions/004-sqlite-state-from-day-one.md) |
| Finding fingerprinting | Content-based hash for deduplication | [OQ-003](../reference/open-questions.md) |
| Deduplication | Skip previously seen/suppressed findings | [overview.md](../architecture/overview.md) §"Deduper / Clusterer" |
| Morning report | Markdown file output, one finding per line with expandable evidence | [overview.md](../architecture/overview.md) §"Morning Report" |
| CLI approve/suppress | Basic CLI commands to approve or suppress findings | [OQ-002](../reference/open-questions.md) |

### Not in MVP scope

| Item | Phase | Source |
|------|-------|--------|
| Docs-drift detector | Phase 2 | [roadmap](../../roadmap/README.md) |
| GitHub issue creation | Phase 5 | [roadmap](../../roadmap/README.md) |
| Web UI | Phase 2+ | [OQ-002](../reference/open-questions.md) |
| Multi-repo support | Phase 3+ | [OQ-005](../reference/open-questions.md) |
| SQL anti-pattern detector | Phase 2+ | [OQ-006](../reference/open-questions.md) |
| Watch mode | Future | [overview.md](../architecture/overview.md) §"Trigger modes" |
| Embeddings-based context | Phase 1 stretch or Phase 2 | [OQ-004](../reference/open-questions.md) |
| Cron/git-hook triggers | Phase 1 stretch — manual CLI is sufficient for MVP | [overview.md](../architecture/overview.md) §"Trigger modes" |

## Architecture Invariants

These hold across all phases and must not be violated:

1. **Detectors are pluggable**: Every detector produces `Finding` objects through the same interface. Adding a detector never requires changing the pipeline.
2. **LLM is replaceable**: Changing the model is a config change. The pipeline works (degraded: no judgment, raw findings only) without any model running.
3. **State is persistent**: Every run reads from and writes to the SQLite state store. There is no stateless mode in production.
4. **Evidence is mandatory**: A finding without evidence is invalid. The system does not surface hunches.
5. **Human approval gates external actions**: No GitHub API calls, no external side effects without explicit user confirmation.
6. **Single repo per run**: Each run targets one repository. Multi-repo is a future concern (OQ-005).

**Source**: [overview.md](../architecture/overview.md); [detector-interface.md](../architecture/detector-interface.md); [ADR-001](../architecture/decisions/001-local-first-execution.md) through [ADR-004](../architecture/decisions/004-sqlite-state-from-day-one.md)

## Required Workflows

1. **Scan**: `sentinel scan <repo-path>` → detectors run → findings gathered + judged → deduped → morning report written.
2. **Review**: User reads morning report markdown. Each finding has severity, confidence, category, one-line summary, expandable evidence.
3. **Suppress**: `sentinel suppress <finding-id>` → finding marked as false positive, excluded from future reports.
4. **Approve**: `sentinel approve <finding-id>` → finding marked for action (GitHub issue creation deferred to Phase 5).
5. **History**: `sentinel history` → view past runs and finding trends.

**Source**: [overview.md](../architecture/overview.md); [OQ-002](../reference/open-questions.md); [roadmap](../../roadmap/README.md)

## Out-of-Scope Items

These are explicitly excluded from the project's vision, not just deferred:

- Implementing code fixes or generating patches
- Making architecture recommendations
- Opening pull requests
- Acting as a CI/CD gate (it's a background advisor, not a blocker)
- Cloud-hosted execution (local-first is a core identity)
- Real-time / in-editor integration (it runs between sessions, not during)

**Source**: [strategy.md](strategy.md) §"What it should not pretend to do"; [positioning.md](positioning.md) §"Explicitly not"

## Risks

| Risk | Likelihood | Impact | Mitigation | Source |
|------|-----------|--------|------------|--------|
| False positive rate too high with 4B model | Medium | High — users stop reading the report | Deterministic-first architecture; LLM is judgment layer, not signal source; suppression mechanism | [ADR-002](../architecture/decisions/002-deterministic-detectors-first.md); [critical-review.md](../analysis/critical-review.md) |
| Morning report too noisy or poorly formatted | Medium | Medium — reduces daily usefulness | Design report format early; < 2 minute scannability constraint | [strategy.md](strategy.md); [OQ-002](../reference/open-questions.md) |
| Embedddings/context quality insufficient | Low-Medium | Medium — LLM judge makes poor decisions on thin context | Start simple (file-proximity), add embeddings incrementally | [OQ-004](../reference/open-questions.md) |
| Fingerprinting breaks on file renames | Medium | Low — temporary dedup failures | Accept and add "similar finding" heuristic later | [OQ-003](../reference/open-questions.md) |
| Ollama dependency creates friction | Low | Low — Ollama is well-established | Document setup clearly; degrade gracefully without model | [ADR-003](../architecture/decisions/003-model-agnostic-via-ollama.md) |

## Unresolved Assumptions

These assumptions are present in the docs but not yet validated:

| Assumption | Status | Reference |
|-----------|--------|-----------|
| Report delivery as markdown file + CLI is sufficient for MVP | Unvalidated — will learn from usage | [OQ-002](../reference/open-questions.md) |
| Content-hash fingerprinting is stable enough for dedup | Unvalidated — needs implementation experience | [OQ-003](../reference/open-questions.md) |
| SQLite-vec is sufficient for vector storage if embeddings are added | Unvalidated | [OQ-004](../reference/open-questions.md) |
| Single-repo design can naturally extend to multi-repo | Unvalidated — schema must be reviewed | [OQ-005](../reference/open-questions.md) |
| Precision@k ≥ 70% is achievable with deterministic detectors + 4B judge | Aspirational — requires eval | [OQ-007](../reference/open-questions.md) |

## Source Basis

Every major claim above is traceable to existing repository documentation:

| Claim | Primary Source | Supporting Sources |
|-------|---------------|-------------------|
| Problem: gap between interactive AI tools and background review | [strategy.md](strategy.md) §"Why this exists" | [brainstorm.md](../archive/brainstorm.md); [positioning.md](positioning.md) |
| Target user: WSL 2 developer with 8 GB VRAM | [strategy.md](strategy.md) §"Target user" | [ADR-001](../architecture/decisions/001-local-first-execution.md); [brainstorm.md](../archive/brainstorm.md) |
| Core concept: local evidence-backed issue triage | [strategy.md](strategy.md) §"Core concept" | [positioning.md](positioning.md); [overview.md](../architecture/overview.md) |
| Non-goals: no fixes, no autonomy, no cloud | [strategy.md](strategy.md) §"What it should not pretend to do" | [positioning.md](positioning.md) |
| Local-first execution | [ADR-001](../architecture/decisions/001-local-first-execution.md) | [strategy.md](strategy.md) §"Why local execution matters" |
| Deterministic detectors as primary signal | [ADR-002](../architecture/decisions/002-deterministic-detectors-first.md) | [overview.md](../architecture/overview.md); [critical-review.md](../analysis/critical-review.md) |
| Model-agnostic via Ollama | [ADR-003](../architecture/decisions/003-model-agnostic-via-ollama.md) | [overview.md](../architecture/overview.md) |
| SQLite state from day one | [ADR-004](../architecture/decisions/004-sqlite-state-from-day-one.md) | [overview.md](../architecture/overview.md) |
| Docs-drift as first-class detector | [ADR-005](../architecture/decisions/005-docs-drift-first-class-detector.md) | [detector-interface.md](../architecture/detector-interface.md) |
| Python implementation | [ADR-007](../architecture/decisions/007-python-implementation-language.md) | — |
| MVP: 3 detectors + judge + state + report | [roadmap](../../roadmap/README.md) §Phase 1 | [detector-interface.md](../architecture/detector-interface.md); [critical-review.md](../analysis/critical-review.md) |
| Pipeline: detect → gather → judge → dedup → report | [overview.md](../architecture/overview.md) §"High-level data flow" | [detector-interface.md](../architecture/detector-interface.md) |
| Precision over breadth | [positioning.md](positioning.md) §"Key warning" | [critical-review.md](../analysis/critical-review.md) |
| < 2 minute review time | [strategy.md](strategy.md) §"Primary output" | [OQ-002](../reference/open-questions.md) |
| Eval metrics: precision@k, FP rate, review time | [OQ-007](../reference/open-questions.md) | [critical-review.md](../analysis/critical-review.md) |
