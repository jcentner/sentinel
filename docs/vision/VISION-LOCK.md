# Vision Lock — Local Repo Sentinel

> **Version**: 6.2
> **Updated**: 2026-04-14
> **Supersedes**: v5.6 ([archived](archive/VISION-LOCK-v5.md))
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

18 pluggable detectors (Python, JS/TS, Go, Rust, cross-artifact, CI/CD, architecture). Four LLM-assisted detectors (semantic-drift, test-coherence, inline-comment-drift, intent-comparison) with benchmark-driven prompt adaptation (binary safe-default, enhanced when quality data supports it — ADR-016) and multi-language support via tree-sitter (Python, JavaScript, TypeScript with regex fallback). Two-phase execution: heuristic detectors run first (parallel via thread pool), building per-file risk signals; LLM detectors then prioritize high-churn files (TD-043). Full pipeline: fingerprint → dedup → context → judge → synthesis → store → report. Async LLM pipeline: concurrent judge (8) and synthesis (4) via ADR-017, giving 4.5x speedup on cloud providers. Pluggable providers (Ollama, OpenAI-compat, Azure). Entry-points plugin system (ADR-012). CLI (21 commands incl. `compare`, `bulk-approve`, `bulk-suppress`, `--json-output`). Web UI (triage, scan config, compatibility matrix, LLM call log, eval dashboard, benchmark). GitHub issue creation. Multi-repo scanning. 1378 tests. Published on PyPI as `repo-sentinel`.

88% confirmation rate on real-world scan (92/104 findings confirmed). 3 repos with annotated ground truth (sample-repo, pip-tools, sentinel). All 18 detectors benchmarked on ≥2 models. See [compatibility matrix](../reference/compatibility-matrix.md) for per-model quality ratings.

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
| 11 | Scan completes in <5 min for 100-finding repos | **Met** — 42 findings in 38s (4.5x speedup), 100-finding estimated <2 min |
| 12 | LLM detectors work for JS/TS repos | **Met** — tree-sitter extraction, all 4 detectors extended, 33 JS/TS tests |

## Architecture Invariants

1. Detectors are pluggable — same `Finding` interface, no pipeline changes needed
2. LLM is replaceable — provider + model are config, pipeline works without any model
3. State is persistent — SQLite with migrations
4. Evidence is mandatory — findings without evidence are invalid
5. Human approval gates external actions
6. Privacy is a user choice — local-first, cloud is explicit opt-in

## Where We're Going

Priority-ordered next investments. Each connects to a validated gap.

### Phase 11: Async pipeline & parallel LLM ✓
**Gap**: TD-016 — serial LLM calls are the only medium-severity bottleneck. 100-finding repos take 7+ min for judging alone. TD-002 — sync detector interface blocks all parallelism.
**What**: Async `ModelProvider` protocol. Concurrent judge calls (bounded concurrency). Async detector interface for LLM-calling detectors. Thread-pool execution for CPU-bound detectors.
**Success**: 100-finding scan completes judge+synthesis in <2 min with cloud provider.
**Result**: ADR-017. Async provider on all 4 providers, async judge (concurrency 8), async synthesis (concurrency 4), parallel Phase 1 detectors via thread pool. 4.5x speedup verified with Azure gpt-5.4-nano. TD-016 resolved.

### Phase 12: Multi-language LLM detectors ✓
**Gap**: All 4 LLM detectors are Python-only via `ast`. JS/TS repos get zero cross-artifact analysis despite being the largest user base after Python.
**What**: Tree-sitter integration for language-agnostic AST extraction. Extend semantic-drift, test-coherence, inline-comment-drift to JS/TS. Language-specific extractors behind a common interface.
**Success**: `sentinel scan` on a JS/TS repo produces LLM-assisted findings with same quality as Python repos.
**Result**: Common extractors module (`sentinel.core.extractors`) with Python AST, tree-sitter (JS/TS), and regex fallback backends. All 4 detectors refactored to use shared extractors. Dynamic code fence labels. 33 JS/TS-specific tests. Tree-sitter stack skill. `multilang` optional dependency group.

### Phase 13: Benchmark & ground truth expansion ✓
**Gap**: TD-045 — ground truth is 1 repo with 50 findings. Most model×detector combos are untested. New detectors (inline-comment-drift, intent-comparison) have zero benchmark data.
**What**: Ground truth for 2-3 more repos. Benchmark all detectors on multiple models. `sentinel llm-log` CLI command. Benchmark results in LLM log for web drill-down (OQ-019).
**Success**: ≥3 repos with annotated ground truth. All detectors benchmarked on ≥2 models.
**Result**: 3 ground truth repos: sample-repo (37 TPs incl. 3 ICD, 2 cloud models with per-category eval), pip-tools (38 annotated deterministic, no LLM GT, 2 cloud models), sentinel (57 annotated + 120 assumed TP). Per-category benchmark split (deterministic vs LLM precision) implemented. ICD rated from real ground truth: nano Fair (~40% FP), mini Excellent (<10% FP). Intent-comparison v1 rated Poor on both nano and mini (>90% FP est, TD-057; superseded by Phase 15 v2 redesign). Judge quality UNTESTED for cloud-small/frontier (benchmark skips judge). `sentinel llm-log` CLI with filtering, stats, JSON.

### Phase 14: CLI/Web parity & polish ✓
**Gap**: 5 CLI features not in web, 4 web features not in CLI. Low-severity tech debt accumulation.
**What**: Web UI for benchmark runs. CLI `sentinel llm-log`, `sentinel compare`, bulk operations. Resolve TD-024 (JSON envelope), TD-041 (docs-drift FP), OQ-016 (message list protocol).
**Success**: Every major workflow achievable from both CLI and web.
**Result**: CLI: `compare` (run-to-run diff), `bulk-approve`, `bulk-suppress` commands. Web: `/benchmark` page with form, per-detector results, save-to-disk. TD-024 partially resolved (JSON error paths standardized). TD-057 mitigated (intent-comparison disabled by default via `enabled_by_default` property). OQ-016 deferred (no current caller). 21 CLI commands, 21 web routes. 1378 tests.

### Phase 15: Intent-comparison v2 — post-LLM filtering + calibration
**Gap**: TD-057 — intent-comparison is the highest-potential detector (multi-artifact triangulation catches what pairwise detectors miss) but has >90% FP rate and is disabled by default. No ground truth exists to measure improvements.
**What**: Seed ICD ground truth in sample-repo. Redesign with structured confidence scoring, concrete FP examples in prompts, post-LLM filtering of vague/low-evidence contradictions, dedup against pairwise detectors.
**Success**: <25% FP rate on cloud-nano on sample-repo. Re-enabled by default with benchmark gate. TD-057 resolved.
**Result**: ICD v2 shipped (3f5654b) with post-LLM filtering. Benchmarked 3 repos x 5 models. Success criterion NOT met for cloud-nano (33% precision / 67% FP on sample-repo, 17 findings on pip-tools). Mini achieves 50% precision (N=1), frontier shows fewest findings (1 on pip-tools). Local 4B/9B also good (1 finding on sample-repo). All ICD ratings are estimates (insufficient ground truth). Detector remains disabled by default. TD-057 partially resolved (cloud benchmarks done, ground truth expansion needed).

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
| Async migration breaks existing tests | Medium | ~~Incremental: async provider first, sync shims for backward compat~~ Resolved: all 1314 tests pass after async migration |
| Tree-sitter adds native dependency | Medium | Optional dep, graceful degradation to regex extraction |

## Changelog

### v6.2 (2026-04-14)
- Phase 15 added: Intent-comparison v2 — post-LLM filtering + calibration
- Human-approved direction from vision expansion proposal (Direction 1)
- Goal: <25% FP rate, re-enable by default, resolve TD-057

### v6.1 (2026-04-13)
- Phase 14 completed: CLI/Web parity & polish
- CLI: added `compare`, `bulk-approve`, `bulk-suppress` (21 commands total)
- Web: added `/benchmark` page (21 routes total)
- TD-024 partially resolved: JSON error paths standardized to `{"error": "..."}`
- TD-057 mitigated: intent-comparison disabled by default via `enabled_by_default` property
- Updated "What Exists Today" with current command/test counts

### v6.0 (2026-04-13)
Major version bump: vision expansion after all v5 goals completed.
- Archived v5.6 to `archive/VISION-LOCK-v5.md`
- Added 4 new phases (11–14): async pipeline, multi-language detectors, benchmark expansion, CLI/Web parity
- Added success criteria #11 (scan performance) and #12 (JS/TS LLM detectors)
- Added async migration and tree-sitter risks
- Phase 11 completed: ADR-017, async provider/judge/synthesis, 4.5x speedup verified, SC#11 met

Older changelog entries available in archived versions and git history.
