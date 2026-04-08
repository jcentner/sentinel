# Vision Lock — Local Repo Sentinel

> **Version**: 4.3
> **Updated**: 2026-04-09
> **Supersedes**: v4.2
> **Status**: Active baseline. Substantive changes require a new version with a changelog entry appended to this file.

## Problem Statement

Developer-facing AI tools focus on helping in the moment — autocomplete, chat, inline edits. There is no tool that works in the background, revisits a repository with fresh context overnight, and surfaces overlooked issues for human review in the morning.

Existing adjacent tools are either PR-scoped reviewers (triggered per diff, not persistent), autonomous agents (implement fixes and open PRs), or static analyzers (powerful but not cross-artifact, not persistent, not summarized). None of them do what a thoughtful colleague does when they look at a codebase after a week of rapid changes: notice that the docs no longer match the code, that a test file no longer tests what it claims, that three dependencies were added but only one is used, that a function grew to 200 lines during a refactor.

The hardest problems to catch during fast development — especially AI-assisted development — are **cross-artifact inconsistencies**: drift between code, docs, tests, config, and dependencies that accumulates silently and compounds.

## Target User

A developer on Windows 11 + WSL 2 Ubuntu with 8 GB VRAM GPUs, comfortable running local models via Ollama or connecting to cloud model APIs, working across multiple projects including a primary role and consulting/client engagements. Privacy matters — client code must never leave the machine unless the user explicitly opts into a cloud provider.

## Core Concept

Local Repo Sentinel is a local, evidence-backed repository issue triage system for overnight code health monitoring. It combines two kinds of analysis:

1. **Deterministic detectors** that scan for structural issues — broken links, lint violations, high complexity, known vulnerabilities, TODO accumulation. These are cheap, fast, and reliable.
2. **LLM-powered cross-artifact analysis** that compares related artifacts (docs vs code, tests vs implementation, config vs usage) and identifies inconsistencies a regex can't catch.

Both kinds of findings flow through a common pipeline: fingerprinting, deduplication, context enrichment, LLM judgment, persistent storage, and a concise morning report. After explicit approval, selected findings can become GitHub issues. A browser-based web UI provides the full triage workflow alongside the CLI.

The LLM serves two roles: (a) as a **judge** that filters and re-prioritizes detector output, and (b) as an **analyst** that directly compares artifacts for semantic drift. Both roles are shipped: the judge evaluates all findings; the semantic-drift detector uses the LLM to compare doc sections against code.

The model provider is **pluggable**: Ollama (local) is the default, but users can configure any OpenAI-compatible provider (Azure OpenAI, OpenAI direct, vLLM, LM Studio, etc.). More powerful models unlock deeper analysis — structured explanations instead of binary signals, subtle intent comparison, detailed reasoning — through **capability-tiered detectors** that declare what model class they need. The pipeline is the product; the model and provider are configuration.

## Explicit Non-Goals

1. **Not a code fixer**: Does not implement fixes, suggest patches, or plan refactors.
2. **Not an architect**: Does not make architecture decisions for the user.
3. **Not autonomous**: Does not take external actions without explicit human approval.
4. **Not a PR reviewer**: Not triggered per-PR or per-diff (though it may run incrementally on changed files).
5. **Not a Copilot replacement**: Complements interactive coding tools; does not compete with them.
6. **Not a cloud service**: Sentinel is not a hosted product. Processing is local by default. Users who configure a cloud model provider choose to send code excerpts to that provider's API — that is their decision, not Sentinel's default behavior.
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
| Opinionated defaults, extensible everything | Works out of the box with Ollama and sensible defaults. Every major axis — model provider, detector set, capability tier — is configurable for users who want different tradeoffs. |

## Technical Constraints

| Constraint | Description |
|-----------|-------------|
| Local-first execution | All inference, embedding, state storage, and report generation on the user's machine by default. Cloud model providers are an explicit opt-in. |
| Pluggable model provider | All model interaction through a `ModelProvider` protocol. Ollama is the default. OpenAI-compatible providers (OpenAI, vLLM, LM Studio) and Azure AI Foundry (Entra ID auth) are supported via config. Provider and model are config, not code. See ADR-010. |
| 8 GB VRAM budget (local) | Local models must fit ~4B parameters at Q4_K_M quantization. Users with cloud providers or larger GPUs are not bound by this. |
| Model-agnostic prompts | Prompts target general instruction-following, not model-specific or provider-specific features |
| SQLite state store | Persistent state; embedded, zero-deployment, single-file |
| Python implementation | Chosen for ML/NLP ecosystem, tree-sitter bindings, native sqlite3 |
| Deterministic-first signals | For issues detectable by static analysis or heuristics, deterministic detectors are primary and the LLM is a judgment layer. For cross-artifact semantic issues (docs vs code, test vs implementation), the LLM is the primary signal source with deterministic evidence gathering. |
| No JS build step | Web UI uses server-rendered templates with progressive enhancement (htmx). No Node/npm. |
| Modular dependencies | Optional dependency groups (`[web]`, `[detectors]`, language-specific linters). Core pipeline has minimal required deps. |

## Pipeline

```
detect → fingerprint → deduplicate → gather context → judge → store → report
```

Deduplication happens before the expensive steps (context gathering, LLM judgment) so only novel, non-suppressed findings consume compute.

## What Exists Today

### Core Pipeline
- **14 pluggable detectors** covering Python (ruff, pip-audit, complexity), JS/TS (ESLint/Biome), Go (golangci-lint), Rust (cargo clippy), dependency auditing, unused dependency detection, dead code / unused exports detection, stale env/config drift detection, docs-drift (broken links + stale references), semantic docs-drift (LLM-powered prose vs code comparison), test-code coherence (LLM-powered test staleness detection), git churn hotspots, and TODO/FIXME scanning
- **Custom detector loading**: external detectors via `detectors_dir` config, auto-registered through `__init_subclass__`
- **Centralized skip-directory management**: `COMMON_SKIP_DIRS` in detector base class, extensible per-detector
- **Embedding-based context gathering**: opt-in via configured provider (default: Ollama), falls back to file-proximity heuristics
- **LLM judge**: structured judgment via configured provider (default: Ollama) with JSON output. System degrades gracefully (raw findings only) when no model is running
- **Finding fingerprinting**: content-hash deduplication, target-aware fingerprinting for docs-drift (same missing file referenced from multiple docs deduplicates correctly), suppression persistence, occurrence tracking
- **Two-pass clustering**: pattern clustering (same detector + normalized title) then directory clustering (3+ findings in shared parent)
- **Morning report**: markdown output, severity-grouped, clustered, with occurrence badges

### Real-World Validation
Tested on a production Next.js + Python project (~102 source files). After iterative FP reduction: 104 findings after dedup, 92 confirmed, 12 FP (88% confirmation rate). Judge time: 179s. Zero inconsistent verdicts. Every confirmed stale link and stale path reference verified as genuinely broken/missing.

### CLI
14 commands: `scan`, `scan-all`, `init`, `doctor`, `show`, `suppress`, `approve`, `create-issues`, `history`, `eval`, `eval-history`, `index`, `serve`, plus global `--version`/`-v`/`-q`. All key commands support `--json-output` for AI agent integration.

### Web UI (`sentinel serve`)
Browser-based triage interface with run review, finding detail, bulk actions, GitHub issue creation, scan configuration, evaluation with trend chart, and run comparison. Dark/light themes.

### GitHub Integration
Issue creation from approved findings with fingerprint-based dedup. Environment variable config (no secrets in config files).

### Multi-repo
`scan-all` scans multiple repos into a shared database. Web UI and CLI display runs across all repos.

### Quality Infrastructure
CI pipeline (GitHub Actions, Python 3.11–3.13, ruff, mypy strict, pytest with coverage). 867 tests.

### Detector Value Assessment (honest)
Based on real-world validation, the current detectors fall into three tiers:

| Tier | Detectors | Capability Tier | Value |
|------|-----------|----------------|-------|
| High | docs-drift (broken links, stale paths), semantic-drift (prose vs code), test-coherence (test staleness) | basic (4B) | Catches real drift that accumulates silently. 97% accuracy for deterministic; semantic-drift and test-coherence binary signals are high-value. Enhanced mode (standard+) provides structured gap analysis and specific inaccuracies. |
| Medium | complexity | none (deterministic) | Surfaces genuinely complex functions. Most useful on first scan; diminishing value on repeat runs. |
| Low | lint-runner, eslint-runner, go-linter, rust-clippy, todo-scanner | none (deterministic) | Duplicate what most dev toolchains already provide. Useful for repos without CI linting. |
| Mixed | git-hotspots | none (deterministic) | Correctly identifies high-churn files but doesn't explain *why* the churn matters. Statistics without insight. |
| Shipped | enhanced test-code coherence | standard (9B+) | Structured analysis: *what* the test misses and *why* it's stale. Activated when model_capability is standard+. |
| Shipped | detailed docs-drift explanations | standard (9B+) | Explain *how* docs are wrong with specific inaccuracies. Activated when model_capability is standard+. |
| Planned | deep semantic analysis | advanced (frontier) | Subtle intent comparison, architecture-level drift. Not yet implemented. |
| Medium | unused-deps | none (deterministic) | Flags declared-but-never-imported dependencies in Python and JS/TS. Catches transitive deps declared unnecessarily and abandoned packages from rapid development. |
| Medium | stale-env | none (deterministic) | Detects drift between .env.example and actual env var usage in code. Catches undocumented vars (MEDIUM) and stale documented vars (LOW). Supports Python (os.environ/os.getenv) and JS (process.env). |
| Medium | dead-code | none (heuristic) | Identifies exported functions, classes, and constants never imported elsewhere. Cross-references Python (ast) and JS/TS (regex) across the codebase. Valuable after AI-assisted rapid development. |
| Mixed | dep-audit | none (deterministic) | Genuinely useful for CVE detection if user doesn't already run audit tools. Limited to Python with root-level project markers. |

The **capability tier** column shows what model class a detector needs. Detectors with higher capability tiers are only useful when a sufficiently powerful model is configured. Users choose their own ceiling.

## Success Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Install, point at repo, get useful morning report | **Met** |
| 2 | Report scannable in < 2 minutes | **Met** |
| 3 | Majority of findings are real or worth reviewing | **Met** — 88% confirmation rate on real-world scan (92/104) |
| 4 | Findings deduplicated across runs | **Met** |
| 5 | Works fully offline except optional GitHub | **Met** |
| 6 | Swap LLM model via config, not code | **Met** |
| 7 | Suppress a FP and it stays suppressed | **Met** |
| 8 | Full triage cycle from the browser without CLI | **Met** |
| 9 | CLI usable by AI agents (JSON output, exit codes) | **Met** |
| 10 | Findings surface issues the developer didn't already know about | **Partially met** — docs-drift catches real blind spots; lint/complexity/todo findings are mostly already visible through existing tools |

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
2. **LLM is replaceable**: changing the model *and provider* is a config change. The pipeline works without any model running.
3. **State is persistent**: every run reads from and writes to the SQLite state store.
4. **Evidence is mandatory**: a finding without evidence is invalid.
5. **Human approval gates external actions**: no GitHub API calls without explicit user confirmation.
6. **Single repo per run**: each run targets one repository.
7. **Parallel extensibility**: new detectors, language integrations, and model providers are isolated modules. Multiple developers or agents can work on different components simultaneously without merge conflicts in core code.
8. **Privacy is a user choice**: local-first by default. Code never leaves the machine unless the user explicitly configures a cloud provider.

## Where We're Going

These are the next areas of investment, roughly priority-ordered. Each connects to a gap identified through real-world validation.

### Phase 6: Cross-artifact LLM detectors — Next priority

The highest-leverage improvement is using the LLM to do what deterministic detectors can't: compare two related artifacts and identify semantic inconsistency. These detectors feed the LLM focused, bounded inputs (one doc section + one code function) and ask specific comparison questions.

**Semantic docs-drift**: ✅ **Shipped.** Feed the LLM a documentation section alongside the code it describes. Ask: "Does this documentation accurately describe this code?" This catches the real docs-drift problem — not broken links, but *stale descriptions*. Implemented as the `semantic-drift` detector using heading-based section chunking and name-matching pairing. Binary "needs_review" / "in_sync" output. Remains to be validated on real projects.

**Test-code coherence**: Feed the LLM a test function alongside its target implementation. Ask: "Does this test meaningfully validate this implementation, or has the implementation changed enough that the test passes trivially or tests the wrong thing?" Harder than docs-drift — requires understanding intent — but even a noisy signal here has high value. May need the 9B model or careful prompt engineering.

**The key product insight**: For both of these, even a simple binary signal — "this doc section needs review" or "this test may be stale" — is high value. The developer doesn't need the LLM to explain *how* the docs are wrong or *what* to fix. Identifying *that* something is out of sync is the hard part. A 4B model can deliver that binary triage signal reliably; detailed explanations are a bonus, not a requirement.

### Phase 6b: High-value deterministic detectors

Detectors that find things existing dev tools don't, without needing the LLM:

**Dead code / unused exports**: ✅ **Shipped.** Uses Python's `ast` module and regex-based JS/TS extraction to identify exported symbols (functions, classes, constants) and cross-reference against imports across the codebase. Symbols exported but never imported elsewhere are flagged. Respects `__all__`, skips private symbols and dunder methods, and excludes test files from generating findings (while counting test imports as usage). Heuristic tier (symbol reachability involves heuristic judgment). Tree-sitter can be added later for more precise multi-language extraction.

**Unused dependencies**: ✅ **Shipped.** Compares declared packages (pyproject.toml / package.json) against actual imports in source code. Flags packages declared but never imported. Handles known package→import name mappings (e.g. Pillow→PIL, PyYAML→yaml). Skips known tool packages (pytest, ruff, etc.). Supports PEP 621, Poetry, requirements.txt, and package.json. Different from dep-audit (which checks for CVEs) — this checks for waste.

**Stale config / env drift**: ✅ **Shipped.** Compares `.env.example` (or `.env.sample`/`.env.template`) against environment variables actually referenced in code. Detects both stale documented vars (in example but never read) and undocumented vars (read in code but not in example). Supports Python (`os.environ`, `os.getenv`, `os.environ.get`) and JS/TS (`process.env`). Filters common system vars (PATH, HOME, CI, etc.).

### Completed (shipped in prior phases)

- **Multi-language repo support**: Python, JS/TS, Go, Rust detectors. Language-neutral detectors work across all.
- **Multi-repo support**: `scan-all` with shared database. Web UI displays all repos.
- **Root-cause finding grouping**: Two-pass clustering in reports and web UI.
- **CLI as AI-agent interface**: `--json-output`, quiet mode, predictable exit codes.
- **Eval metrics dashboard**: Persistent eval results, trend charts, history.
- **Model benchmarking**: 4B recommended for 8GB VRAM. Documented.
- **Packaging**: CI/CD, wheel, CONTRIBUTING.md.

### Phase 7: Provider abstraction — After Phase 6/6b

Extract a `ModelProvider` protocol so the pipeline is provider-agnostic, not just model-agnostic. See ADR-010.

- **`OllamaProvider`**: Current behavior extracted. Remains the zero-config default.
- **`OpenAICompatibleProvider`**: Covers OpenAI direct and any OpenAI-compatible endpoint (vLLM, LM Studio, Together, etc.).
- **`AzureProvider`**: Azure AI Foundry with Entra ID bearer token auth via `az` CLI. Uses `max_completion_tokens` for newer model compatibility.
- **Config**: `provider = "ollama"` (default), `provider = "openai"` with `api_base`/`api_key_env`, or `provider = "azure"` with `api_base`.
- Judge, semantic-drift, and docs-drift consolidate behind `provider.generate()` instead of raw `httpx.post` to Ollama.
- Embedding calls consolidate behind `provider.embed()`.

### Phase 8: Capability-tiered detectors — In Progress

With provider abstraction in place, detectors adapt their behavior based on model capability:

| Capability Tier | Model Class | Detectors / Enhancements |
|-----------------|-------------|-------------------------|
| `basic` (4B+) | qwen3.5:4b | ✅ Judge, semantic-drift binary signal, test-coherence binary signal |
| `standard` (9B+ or small cloud) | qwen3:9b, gpt-5.4-nano | ✅ Enhanced test-coherence with structured gap analysis, enhanced semantic-drift with specific inaccuracies |
| `advanced` (frontier cloud) | GPT-5.4-mini, GLM-5 | Deep intent comparison, architecture-level drift, subtle semantic analysis |

`CapabilityTier` enum and infrastructure shipped. Detectors declare their tier via `capability_tier` property. Runner warns when a detector's tier exceeds the configured `model_capability`. Both semantic-drift and test-coherence adapt: basic mode gives binary signal; standard+ mode gives structured analysis with severity, specific gaps/inaccuracies, and higher confidence.

Capability tiers are **informational, not enforced** — the system warns if a detector's declared tier exceeds the configured model's expected capability, but does not block execution.

### PyPI publication — After Phase 8

Publish to PyPI. Packaging is ready (wheel, CI/CD, CONTRIBUTING.md). Needs credentials and final release workflow.

## Out of Scope (permanent)

These are explicitly excluded from the project's vision, not deferred:

- Implementing code fixes or generating patches
- Making architecture recommendations
- Opening pull requests
- Cloud-hosted execution (Sentinel is not a hosted service; cloud *model providers* are supported, but Sentinel itself runs locally)
- Real-time / in-editor integration
- Built-in scheduling (use system cron/systemd timers)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM judge fabricates reasoning to confirm noise | **Observed** | High | Detector precision matters more than judge sophistication. Fix FPs at the detector level. Better to give the judge 1 good finding than 2 duplicates (it will fabricate reasons to confirm both). |
| Semantic detectors too noisy at 4B | Medium | High | Start with binary "needs review" signal, not detailed explanations. Use small focused context windows. Validate on real repos before shipping. |
| FP rate too high erodes trust | Medium | High | Deterministic-first for structural issues; suppression mechanism; 88% confirmation rate achieved through iterative FP reduction |
| Most detectors duplicate existing dev tooling | **Observed** | Medium | Accepted for now — lint/complexity/todo detectors provide value for repos without CI linting. Focus new investment on cross-artifact analysis that nothing else does. |
| Fingerprinting breaks on file renames | Medium | Low | Accept; add similar-finding heuristic later |
| Ollama dependency creates friction | Low | Low | Resolved by ADR-010 — provider is pluggable, Ollama is just the default |
| Provider proliferation dilutes focus | Medium | Medium | Ship exactly two providers (Ollama, OpenAI-compatible). OpenAI-compatible covers Azure, OpenAI, vLLM, LM Studio. No bespoke integrations. Entry-point plugin system deferred unless a third provider type emerges. |
| Privacy story requires nuance | Low | Medium | "Local-first by default" is clear and honest. Cloud opt-in logs a startup warning. Docs state the tradeoff explicitly. |

## Changelog

### v4.3
Phase 8 Slice 1: capability-tiered detectors infrastructure + enhanced modes shipped.
- **CapabilityTier** enum added: NONE, BASIC, STANDARD, ADVANCED
- **Detector ABC** extended: `capability_tier` property with default NONE
- **Runner** warns when detector tier exceeds model capability
- **SentinelConfig**: `model_capability` field (default: basic)
- **semantic-drift** enhanced: structured specifics, severity, higher confidence when standard+
- **test-coherence** enhanced: structured gaps, severity, higher confidence when standard+
- **Detector Value Assessment**: enhanced modes moved from Planned to Shipped
- **Phase 8** marked In Progress, standard tier detectors shipped
- **What Exists Today**: 14 detectors, 873 tests

### v4.2
Phase 6b complete: all three deterministic detectors shipped (unused-deps, stale-env, dead-code).
- **What Exists Today** updated: 14 detectors (was 12), stale-env and dead-code added to value assessment
- **Detector Value Assessment** updated: stale-env added as Medium tier, dead-code added as Medium tier
- **Where We're Going** updated: stale-env and dead-code marked as shipped. Phase 6b complete.
- **Provider list** updated: Azure provider shipped (3 providers: Ollama, OpenAI-compatible, Azure with Entra ID)
- **Ground truth** updated: sample-repo now includes 4 dead-code expected findings (17 total expected TPs)

### v4.1
Test-code coherence detector shipped (Phase 6 Slice 2, completing Phase 6).
- **What Exists Today** updated: 11 detectors (was 10), test-coherence added to high-value tier
- **Detector Value Assessment** updated: test-coherence moved from Planned to High tier
- **LLM analyst role** fully shipped: both cross-artifact detectors (semantic-drift + test-coherence) now operational
- **OQ-009** partially resolved: detector implemented with 4B prompts, real-world validation pending

### v4.0 (2026-04-07)
Provider abstraction and capability-tiered detector vision.
- **Core concept** updated: model provider is pluggable (Ollama default, OpenAI-compatible supported). More powerful models unlock deeper analysis through capability-tiered detectors.
- **Technical constraints** updated: "Ollama as model interface" replaced with "Pluggable model provider" (ADR-010). VRAM budget scoped to local models. Provider and model are config, not code.
- **Product constraints** updated: added "Opinionated defaults, extensible everything" principle.
- **Non-goals** clarified: "Not a cloud service" refined — Sentinel runs locally, but cloud model providers are a user choice.
- **Architecture invariants** updated: LLM replaceable now covers provider + model. New invariant #8: privacy is a user choice. Parallel extensibility includes model providers.
- **Detector Value Assessment** updated: capability tier column added. Planned detectors now show which model class enables them.
- **Where We're Going** updated: Phase 7 (provider abstraction) and Phase 8 (capability-tiered detectors) added after existing phases. PyPI publication moved to after Phase 8. Existing Phase 6/6b items unchanged.
- **Out of Scope** clarified: cloud-hosted execution distinguished from cloud model providers.
- **Risks** updated: Ollama friction resolved (ADR-010). New risks: provider proliferation, privacy story nuance.
- ADR-003 superseded by ADR-010.
- Cross-doc updates: copilot-instructions.md, code-review.prompt.md, detector-interface.md, architecture overview, strategy, open-questions (OQ-010 added, OQ-009 updated), glossary (4 new terms), roadmap README and phase-6 plan, ADR-001 note added.

### v3.1 (2026-04-07)
Semantic docs-drift detector shipped (Phase 5 Slice 1).
- **Core concept** updated: LLM analyst role now partially shipped (semantic-drift detector)
- **What Exists Today** updated: 10 detectors (was 9), semantic-drift added to high-value tier
- **Detector Value Assessment** updated: semantic-drift in high tier, test-code coherence planned
- **Where We're Going** updated: semantic docs-drift marked as shipped, test-code coherence remains next

### v3.0 (2026-04-07)
Strategic recalibration based on critical analysis and real-world validation.
- **Problem statement** sharpened: cross-artifact inconsistency is the core unsolved problem, not lint aggregation
- **Core concept** reframed: LLM has two roles — judge (shipped) and analyst (next frontier)
- **Technical constraints** nuanced: deterministic-first for structural issues; LLM as primary signal source for cross-artifact semantic analysis
- **What Exists Today** updated: 626 tests, 90% coverage, real-world validation results (88% confirmation rate), added honest Detector Value Assessment table
- **Risks** updated: replaced speculative risks with observed ones (LLM fabricates reasoning, most detectors duplicate existing tools)
- **Where We're Going** rewritten: Phase 5 (semantic docs-drift, test-code coherence), Phase 5b (dead code, unused deps, stale config). Key insight: even a binary "needs review" signal is the high-value product.
- **Success criterion #10** added: "Findings surface issues the developer didn't already know about" — partially met
- Archived v2.2 as [archive/VISION-LOCK-v2.md](archive/VISION-LOCK-v2.md)

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
