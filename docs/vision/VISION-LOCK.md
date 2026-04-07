# Vision Lock — Local Repo Sentinel

> **Version**: 3.1
> **Updated**: 2026-04-07
> **Supersedes**: v3.0 (2026-04-07)
> **Status**: Active baseline. Substantive changes require a new version with a changelog entry appended to this file.

## Problem Statement

Developer-facing AI tools focus on helping in the moment — autocomplete, chat, inline edits. There is no tool that works in the background, revisits a repository with fresh context overnight, and surfaces overlooked issues for human review in the morning.

Existing adjacent tools are either PR-scoped reviewers (triggered per diff, not persistent), autonomous agents (implement fixes and open PRs), or static analyzers (powerful but not cross-artifact, not persistent, not summarized). None of them do what a thoughtful colleague does when they look at a codebase after a week of rapid changes: notice that the docs no longer match the code, that a test file no longer tests what it claims, that three dependencies were added but only one is used, that a function grew to 200 lines during a refactor.

The hardest problems to catch during fast development — especially AI-assisted development — are **cross-artifact inconsistencies**: drift between code, docs, tests, config, and dependencies that accumulates silently and compounds.

## Target User

A developer on Windows 11 + WSL 2 Ubuntu with 8 GB VRAM GPUs, comfortable running local models via Ollama, working across multiple projects including a primary role and consulting/client engagements. Privacy matters — client code must never leave the machine.

## Core Concept

Local Repo Sentinel is a local, evidence-backed repository issue triage system for overnight code health monitoring. It combines two kinds of analysis:

1. **Deterministic detectors** that scan for structural issues — broken links, lint violations, high complexity, known vulnerabilities, TODO accumulation. These are cheap, fast, and reliable.
2. **LLM-powered cross-artifact analysis** that compares related artifacts (docs vs code, tests vs implementation, config vs usage) and identifies inconsistencies a regex can't catch.

Both kinds of findings flow through a common pipeline: fingerprinting, deduplication, context enrichment, LLM judgment, persistent storage, and a concise morning report. After explicit approval, selected findings can become GitHub issues. A browser-based web UI provides the full triage workflow alongside the CLI.

The LLM serves two roles: (a) as a **judge** that filters and re-prioritizes detector output, and (b) as an **analyst** that directly compares artifacts for semantic drift. Both roles are shipped: the judge evaluates all findings; the semantic-drift detector uses the LLM to compare doc sections against code.

## Explicit Non-Goals

1. **Not a code fixer**: Does not implement fixes, suggest patches, or plan refactors.
2. **Not an architect**: Does not make architecture decisions for the user.
3. **Not autonomous**: Does not take external actions without explicit human approval.
4. **Not a PR reviewer**: Not triggered per-PR or per-diff (though it may run incrementally on changed files).
5. **Not a Copilot replacement**: Complements interactive coding tools; does not compete with them.
6. **Not a cloud service**: All processing is local except the optional GitHub issue creation API call.
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

## Technical Constraints

| Constraint | Description |
|-----------|-------------|
| Local-first execution | All inference, embedding, state storage, and report generation on the user's machine |
| 8 GB VRAM budget | Models must fit ~4B parameters at Q4_K_M quantization |
| Ollama as model interface | All model interaction through Ollama API; model names are config, not code |
| Model-agnostic prompts | Prompts target general instruction-following, not model-specific features |
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
- **10 pluggable detectors** covering Python (ruff, pip-audit, complexity), JS/TS (ESLint/Biome), Go (golangci-lint), Rust (cargo clippy), dependency auditing, docs-drift (broken links + stale references), semantic docs-drift (LLM-powered prose vs code comparison), git churn hotspots, and TODO/FIXME scanning
- **Custom detector loading**: external detectors via `detectors_dir` config, auto-registered through `__init_subclass__`
- **Centralized skip-directory management**: `COMMON_SKIP_DIRS` in detector base class, extensible per-detector
- **Embedding-based context gathering**: opt-in via Ollama, falls back to file-proximity heuristics
- **LLM judge**: structured judgment via Ollama with JSON output. System degrades gracefully (raw findings only) when no model is running
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
CI pipeline (GitHub Actions, Python 3.11–3.13, ruff, mypy strict, pytest with coverage). 626 tests, 90% code coverage.

### Detector Value Assessment (honest)
Based on real-world validation, the current detectors fall into three tiers:

| Tier | Detectors | Value |
|------|-----------|-------|
| High | docs-drift (broken links, stale paths), semantic-drift (prose vs code) | Catches real drift that accumulates silently. 97% accuracy for deterministic; semantic-drift binary signal is high-value. |
| Medium | complexity | Surfaces genuinely complex functions. Most useful on first scan; diminishing value on repeat runs. |
| Low | lint-runner, eslint-runner, go-linter, rust-clippy, todo-scanner | Duplicate what most dev toolchains already provide. Useful for repos without CI linting. |
| Mixed | git-hotspots | Correctly identifies high-churn files but doesn't explain *why* the churn matters. Statistics without insight. |
| Planned | test-code coherence | Compare tests against implementation for semantic staleness. Not yet implemented. |
| Mixed | dep-audit | Genuinely useful for CVE detection if user doesn't already run audit tools. Limited to Python with root-level project markers. |

The current detectors are predominantly **surface-level structural checks**. The higher-value analysis — semantic comparison of docs vs code, tests vs implementation, config vs usage — is identified but not yet implemented.

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
2. **LLM is replaceable**: changing the model is a config change. The pipeline works without any model running.
3. **State is persistent**: every run reads from and writes to the SQLite state store.
4. **Evidence is mandatory**: a finding without evidence is invalid.
5. **Human approval gates external actions**: no GitHub API calls without explicit user confirmation.
6. **Single repo per run**: each run targets one repository.
7. **Parallel extensibility**: new detectors and language integrations are isolated modules. Multiple developers or agents can work on different language support packages simultaneously without merge conflicts in core code.

## Where We're Going

These are the next areas of investment, roughly priority-ordered. Each connects to a gap identified through real-world validation.

### Phase 5: Cross-artifact LLM detectors — Next priority

The highest-leverage improvement is using the LLM to do what deterministic detectors can't: compare two related artifacts and identify semantic inconsistency. These detectors feed the LLM focused, bounded inputs (one doc section + one code function) and ask specific comparison questions.

**Semantic docs-drift**: ✅ **Shipped.** Feed the LLM a documentation section alongside the code it describes. Ask: "Does this documentation accurately describe this code?" This catches the real docs-drift problem — not broken links, but *stale descriptions*. Implemented as the `semantic-drift` detector using heading-based section chunking and name-matching pairing. Binary "needs_review" / "in_sync" output. Remains to be validated on real projects.

**Test-code coherence**: Feed the LLM a test function alongside its target implementation. Ask: "Does this test meaningfully validate this implementation, or has the implementation changed enough that the test passes trivially or tests the wrong thing?" Harder than docs-drift — requires understanding intent — but even a noisy signal here has high value. May need the 9B model or careful prompt engineering.

**The key product insight**: For both of these, even a simple binary signal — "this doc section needs review" or "this test may be stale" — is high value. The developer doesn't need the LLM to explain *how* the docs are wrong or *what* to fix. Identifying *that* something is out of sync is the hard part. A 4B model can deliver that binary triage signal reliably; detailed explanations are a bonus, not a requirement.

### Phase 5b: High-value deterministic detectors

Detectors that find things existing dev tools don't, without needing the LLM:

**Dead code / unused exports**: Use tree-sitter to identify exported symbols (functions, classes, constants) and cross-reference against imports across the codebase. Symbols exported but never imported elsewhere are likely dead code. Especially valuable after AI-assisted rapid development where approaches get generated, tried, and abandoned.

**Unused dependencies**: Compare installed packages (from pyproject.toml / package.json) against actual imports in source code. Flag packages that are declared but never imported. Different from dep-audit (which checks for CVEs) — this checks for waste.

**Stale config / env drift**: Compare `.env.example` against environment variables actually referenced in code (via `os.environ`, `process.env`). Flag variables that exist in the example but are never read, or that code reads but the example doesn't document.

### Completed (shipped in prior phases)

- **Multi-language repo support**: Python, JS/TS, Go, Rust detectors. Language-neutral detectors work across all.
- **Multi-repo support**: `scan-all` with shared database. Web UI displays all repos.
- **Root-cause finding grouping**: Two-pass clustering in reports and web UI.
- **CLI as AI-agent interface**: `--json-output`, quiet mode, predictable exit codes.
- **Eval metrics dashboard**: Persistent eval results, trend charts, history.
- **Model benchmarking**: 4B recommended for 8GB VRAM. Documented.
- **Packaging**: CI/CD, wheel, CONTRIBUTING.md. *Remaining*: PyPI publish.

## Out of Scope (permanent)

These are explicitly excluded from the project's vision, not deferred:

- Implementing code fixes or generating patches
- Making architecture recommendations
- Opening pull requests
- Cloud-hosted execution
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
| Ollama dependency creates friction | Low | Low | Degrade gracefully; document setup clearly |

## Changelog

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
