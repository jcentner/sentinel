# Vision Lock — Local Repo Sentinel

> **Version**: 5.3
> **Updated**: 2026-04-13
> **Supersedes**: v4.9 ([archived](archive/VISION-LOCK-v4.md))
> **Status**: Active baseline. Substantive changes require a new version with a changelog entry appended to this file.

## Problem Statement

Developer-facing AI tools focus on helping in the moment — autocomplete, chat, inline edits. None work in the background, revisit a repository overnight, and surface overlooked issues the next morning.

The hardest problems during fast development — especially AI-assisted — are **cross-artifact inconsistencies**: drift between code, docs, tests, config, and dependencies that accumulates silently and compounds.

## Target User

A developer on Windows 11 + WSL 2 Ubuntu with 8 GB VRAM GPUs, comfortable with local models via Ollama or cloud APIs, working across multiple projects. Privacy matters — client code must never leave the machine unless the user explicitly opts into a cloud provider.

## Core Concept

Local Repo Sentinel combines **deterministic detectors** (structural issues: broken links, lint, complexity, CVEs, dead code) with **LLM-powered cross-artifact analysis** (docs vs code, tests vs implementation, config vs usage). Both flow through a common pipeline: fingerprinting → dedup → context → judge → store → report. The LLM is both a **judge** (filters detector output) and an **analyst** (directly compares artifacts for semantic drift).

The model provider is **pluggable** (Ollama default, OpenAI-compatible supported). More powerful models unlock deeper analysis through **benchmark-driven prompt adaptation** — the system uses empirical quality data, not assumed tiers, to decide how to use each model (ADR-016). The pipeline is the product; model and provider are configuration.

## Explicit Non-Goals

1. Not a code fixer — no patches, no refactors
2. Not autonomous — no external actions without human approval
3. Not a PR reviewer — not triggered per-diff
4. Not a cloud service — runs locally; cloud *providers* are opt-in
5. Not a CI/CD gate — background advisor, not blocker

## Product Constraints

| Constraint | Description |
|-----------|-------------|
| Human approval gate | No GitHub issue creation without explicit approval |
| Morning report scannability | Scannable in under 2 minutes |
| Evidence-backed findings | Every finding cites concrete evidence |
| Precision over breadth | 3 real issues beats 20 noisy ones |
| Dual interface | CLI (automation, scripting, agents) + web UI (discovery, triage, configuration). Feature parity — web is first-class, not read-only (ADR-015). |
| Model-detector transparency | Empirical quality ratings visible before scanning — reference benchmarks shipped, user benchmarks accumulated via `sentinel benchmark` |
| Modular by default | Optional deps; plugin ecosystem via entry-points |

## Technical Constraints

| Constraint | Description |
|-----------|-------------|
| Local-first | All processing on user's machine by default. Cloud is opt-in. |
| Pluggable provider | `ModelProvider` protocol. Ollama default, OpenAI-compat supported (ADR-010). |
| 8 GB VRAM budget | Local models ≤4B at Q4_K_M. Cloud users not bound by this. |
| SQLite state store | Embedded, zero-deployment, single-file |
| Python | ML/NLP ecosystem, ast module, native sqlite3 |
| No JS build step | Server-rendered templates + htmx |

## What Exists Today

14 pluggable detectors (Python, JS/TS, Go, Rust, cross-artifact). Two LLM-assisted detectors (semantic-drift, test-coherence) with benchmark-driven prompt adaptation (binary safe-default, enhanced when quality data supports it — ADR-016). Two-phase execution: heuristic detectors run first, building per-file risk signals; LLM detectors then prioritize high-churn files (TD-043). Full pipeline: fingerprint → dedup → context → judge → synthesis → store → report. Pluggable providers (Ollama, OpenAI-compat, Azure). Entry-points plugin system (ADR-012). CLI (13 commands, `--json-output`). Web UI (triage, scan config, compatibility matrix, LLM call log, eval dashboard). GitHub issue creation. Multi-repo scanning. 1134 tests. Published on PyPI as `repo-sentinel`.

88% confirmation rate on real-world scan (92/104 findings confirmed). See [compatibility matrix](../reference/compatibility-matrix.md) for per-model quality ratings.

## Success Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Install → scan → useful report | **Met** |
| 2 | Report scannable in <2 min | **Met** |
| 3 | Majority of findings are real | **Met** (88%) |
| 4 | Deduplicated across runs | **Met** |
| 5 | Works fully offline | **Met** |
| 6 | Swap model via config | **Met** |
| 7 | Suppress FP permanently | **Met** |
| 8 | Full triage in browser | **Met** |
| 9 | CLI usable by AI agents | **Met** |
| 10 | Surfaces unknown issues | **Partial** — cross-artifact detectors deliver; lint/todo overlap with existing tools |

## Architecture Invariants

1. Detectors are pluggable — same `Finding` interface, no pipeline changes needed
2. LLM is replaceable — provider + model are config, pipeline works without any model
3. State is persistent — SQLite with migrations
4. Evidence is mandatory — findings without evidence are invalid
5. Human approval gates external actions
6. Privacy is a user choice — local-first, cloud is explicit opt-in

## Where We're Going

Priority-ordered next investments. Each connects to a validated gap.

### Web UI as first-class interaction surface
Settings page editable (ADR-015). Detectors page with inline model/toggle config, doctor health check page, LLM call log viewer. Remaining: `index` command page.

### Phase 10: Advanced detectors
New detectors requiring stronger models (benchmark data will guide minimum model recommendations):
- CI/CD config drift (basic) — stale paths in GitHub Actions, Dockerfiles
- Inline comment drift (advanced) — docstring accuracy vs adjacent code
- Intent comparison (advanced) — multi-artifact triangulation
- Architecture drift (advanced) — import graph vs documented architecture

### Cross-detector intelligence — shipped
Two-phase execution (TD-043): heuristic detectors run first, `risk_signals` extracted from git-hotspots, LLM detectors sort files by risk. test-coherence prioritizes tests for high-churn implementation files.

## Out of Scope (permanent)

- Implementing fixes or generating patches
- Opening pull requests
- Cloud-hosted execution
- Real-time / in-editor integration
- Built-in scheduling (use system cron/timers)

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM judge fabricates reasoning | High | Fix FPs at detector level, not judge level |
| test-coherence noisy at 4B | High | Binary signal + benchmark-driven quality warnings + per-detector model routing (ADR-016) |
| FP rate erodes trust | High | 88% confirmation rate via iterative FP reduction |
| Most detectors duplicate dev tooling | Medium | Focus investment on cross-artifact analysis |

## Changelog

### v5.3 (2026-04-13)
Cross-detector intelligence shipped (TD-043). LLM call log viewer.
- Two-phase execution: heuristic detectors → risk signals → LLM detectors
- git-hotspots findings feed `risk_signals` to LLM detectors via `DetectorContext`
- test-coherence prioritizes high-churn implementation files
- `/llm-log` web page with filters, pagination, expandable prompt/response drill-down
- Cross-detector intelligence moved from "Where We're Going" to shipped

### v5.2 (2026-04-12)
Benchmark-driven model quality (ADR-016, supersedes ADR-011 tier system).
- Model quality ratings are empirical per-model×detector, not tier-based taxonomy
- Prompt strategy (binary vs enhanced) driven by benchmark data, not config label
- Reference benchmarks shipped; user benchmarks accumulated via `sentinel benchmark`
- `CapabilityTier` config preserved for backward compat as explicit override
- Benchmark drill-down planned for power users (inspect prompts, context, outputs)

### v5.1 (2026-04-11)
Strategic document reset — pruned from 432 to <200 lines per document health rules.
- Archived v4.9 to `archive/VISION-LOCK-v4.md`
- Compressed "What Exists Today" to product-level summary (was per-detector/per-command inventory)
- Removed detailed per-phase shipping history (lives in archived versions and git history)
- Removed detector value assessment table (moved to `docs/reference/compatibility-matrix.md`)
- Removed evaluation criteria table (captured in ADR-008)
- Added "Web UI as first-class configuration surface" as top priority in Where We're Going
- Trimmed changelog to 2 most recent entries; older entries in archived versions
