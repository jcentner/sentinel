# How Sentinel Was Built: A Project History

> A narrative account of building Local Repo Sentinel from idea to working product, intended as source material for blog posts.

## Timeline at a Glance

| Date | What happened |
|------|--------------|
| Mar 28, 2026 | Initial brainstorm, architecture docs, 8 ADRs, competitive landscape analysis |
| Apr 3 | Autopilot prep — agent configuration, builder instructions |
| Apr 4, morning | **Session 1–2**: Vision lock, Phase 1 MVP built end-to-end (15 slices, 129 tests) |
| Apr 4, afternoon | **Session 3**: Phase 2 docs-drift detector, TODO scanner FP reduction, 170 tests |
| Apr 4, late afternoon | **Session 4**: Code reviews, precision fixes, eval CLI, ground truth test harness |
| Apr 4, evening | **Session 5**: Migration framework, persistence scoring, git-hotspots, GitHub integration, 217 tests |
| Apr 5 | **Session 6–14**: Web UI, incremental scanning, embeddings, complexity detector, JSON CLI, eval trends, Go/Rust/ESLint detectors, run comparison. 220→575 tests |
| Apr 6 | **Session 15–17**: CLI polish (init, scan-all, doctor), CI pipeline, packaging for PyPI, CONTRIBUTING.md. 575→614 tests |
| Apr 6 (late) | **Session 18**: Model benchmarking (4B vs 9B), structured JSON output, coverage reporting. Vision lock v2.2 |
| Apr 7, morning | **Session 19**: Real-world validation on external repo (wyoclear). 7 commits fixing FPs. 614→626 tests |
| Apr 7, afternoon | **Session 20**: Strategic recalibration. Vision lock v3.0 — cross-artifact analysis as core differentiator |
| Apr 7 (late) | Template extraction — autonomous workflow extracted into reusable copier template |
| Apr 9 | **Phase 10**: Git-hotspots enrichment (TD-012), per-detector providers (OQ-012+ADR-013), benchmarking system, sample-repo expansion (7/14 detectors). 630→971 tests |

**Total wall-clock from first code commit to feature-complete MVP: ~12 hours across one day.**
**Total from brainstorm to 630 tests and strategic maturity: ~10 days, ~20 autonomous sessions.**

## The Numbers

| Metric | At Session 5 (Apr 5) | Current (Apr 7) |
|--------|---------------------|------------------|
| Source code (Python) | ~3,600 lines / 25 files | ~7,500 lines / 37 files |
| Test code | ~3,100 lines / 23 files | ~8,400 lines / 30+ files |
| Tests passing | 220 | 630 |
| Detectors | 5 | 9 |
| CLI commands | 6 | 9 (scan, suppress, approve, history, eval, create-issues, init, scan-all, doctor) |
| ADRs written | 8 | 8 |
| Documentation files | 26 | 35 |
| Git commits | 46 | 155 |
| External runtime deps | 2 (click, httpx) | 2 (click, httpx) |
| Web UI | — | Full (htmx, bulk triage, eval trends, run comparison) |
| CI | — | GitHub Actions (Python 3.11/3.12/3.13, 90% coverage) |
| Language support | Python repos | Python, TypeScript/JS, Go, Rust repos |

## Phase 0: The Brainstorm (Mar 28)

The project started as a structured brainstorm exploring a gap in the developer tooling landscape. The observation: most AI coding tools help *in the moment* — autocomplete, chat, code generation. Nothing works *in the background*, revisiting a repo overnight to surface overlooked issues for morning review.

The initial brainstorm document defined the core framing: **"a local, evidence-backed repository issue triage system for overnight code health monitoring."** The word "local" was load-bearing — client code never leaves the machine. The word "evidence-backed" set the quality bar — no vague AI opinions, only findings that cite specific code, lint output, or git history.

The first day produced no code but a significant amount of design work:

- **8 Architecture Decision Records** covering local-first execution, deterministic detectors over LLM-primary detection, model-agnostic design via Ollama, SQLite from day one, docs-drift as first-class, Copilot agent as dev tool, Python as language, and evaluation criteria before implementation
- **A competitive landscape analysis** mapping PR-time reviewers (jstar-code-review, PR-Guardian-AI), autonomous executors (night-watch-cli), static analyzers (ruff, Semgrep, SQLFluff), and documentation testing tools
- **A critical review** that honestly evaluated the brainstorm — identifying 6 gaps including vague detector architecture, missing docs-drift as a use case, undefined trigger model, model dependency risk, and no eval criteria
- **7 open questions** tracked formally, ranging from implementation language to fingerprinting strategy to evaluation metrics

### Key design decisions made before writing any code

1. **Deterministic detectors first, LLM as judgment layer** (ADR-002) — A 4B local model is not reliable enough for open-ended code review. Letting it freely scan a repo produces plausible-sounding noise. Instead, deterministic tools (linters, dependency auditors, grep patterns) produce candidate findings, and the LLM evaluates them.

2. **Local-first, no cloud calls** (ADR-001) — Privacy for client repos, zero marginal cost after hardware investment, works offline. The only external call is the optional GitHub API for issue creation.

3. **SQLite state from day one** (ADR-004) — Deduplication is a trust feature. If the same TODO appears in every morning report, the tool is dead. Persistent state enables fingerprinting, suppression, and run history from the first scan.

4. **Evaluation criteria before code** (ADR-008) — Six metrics defined upfront: precision@k ≥70%, false positive rate <30%, review time <2 minutes, 100% repeatability for deterministic detectors. This prevented "it works because I say so."

## Phase 1: MVP Core (Apr 4, Morning)

The MVP was built in 15 ordered implementation slices, each independently testable and committable. The entire phase took one morning session.

### Build order

The dependency chain drove the slice ordering:

1. **Project scaffolding** — pyproject.toml, entry point, tool config
2. **Data models** — `Finding`, `Evidence`, `DetectorContext` as Python dataclasses with validation
3. **SQLite state store** — Schema, migrations, finding CRUD, run tracking, suppressions
4. **Detector base class** — Abstract interface + registry pattern for auto-discovery
5. **TODO scanner** — Regex for TODO/FIXME/HACK/XXX in comment lines, git blame for age
6. **Lint runner** — Shells out to `ruff check --output-format=json`, maps rule prefixes to severities
7. **Dep audit** — Shells out to `pip-audit --format=json`, parses CVE data
8. **Fingerprinting + dedup** — SHA256 hash of (detector, category, file_path, normalized_content), truncated to 16 hex chars
9. **Context gatherer** — File-proximity heuristics: ±5 lines, naming-convention test file matching, git log
10. **LLM judge** — Sends finding + evidence to Ollama, parses structured JSON verdict (is_real, adjusted_severity, summary)
11. **Report generator** — Markdown morning report grouped by severity, one line per finding, expandable evidence
12. **Pipeline runner** — Orchestrates: detect → fingerprint → dedup → gather context → judge → store → report
13. **CLI** — Click-based: `sentinel scan`, `suppress`, `approve`, `history`
14. **Integration tests** — End-to-end pipeline test with sample repo
15. **Repeatability test** — Run detectors twice on same input, assert identical output

### Architecture in action

The pipeline order was revised from the original vision during implementation:

- **Original spec**: detect → gather context → judge → deduplicate → report
- **Implemented**: detect → fingerprint → deduplicate → gather context → judge → store → report

Rationale: running context gathering and LLM inference on findings that will be deduplicated or suppressed wastes compute. This was documented as VISION-REVISION-001 — the first and only revision to the locked vision.

### Graceful degradation

A key design point: the system works without Ollama. If the LLM isn't running, detectors still produce findings, fingerprinting and dedup still work, the report still generates. You just get raw, unjudged findings. This was tested from day one and was non-negotiable.

**End of Phase 1: 129 tests passing, 3 detectors, full CLI, lint clean.**

## Phase 2: Docs-Drift (Apr 4, Afternoon)

ADR-005 had identified docs-drift as a first-class detector category from the start. The reasoning: documentation inconsistency is common, hard to catch with existing linters, and a natural fit for the deterministic + LLM comparison approach.

### Three detection modes

1. **Stale references** (deterministic, 95% confidence) — Parse markdown for links and inline code paths, check if referenced files exist. Dead links are an objective fact, not a judgment call.

2. **Dependency drift** (deterministic, 90% confidence) — Compare `pip install` commands in README code blocks against what's actually declared in `pyproject.toml`/`requirements.txt`. Mismatches between install instructions and reality are a classic docs-drift pattern.

3. **Doc-code comparison** (LLM-assisted, 60–80% confidence) — For key docs (README, CONTRIBUTING), extract code blocks and gather the corresponding source. Ask the LLM: "Does this documentation accurately describe this code?" This catches semantic drift that regex can't — e.g., a README describing a CLI flag that was renamed.

### False positive engineering

The TODO scanner was also refined in this phase. The original version had false positives from:
- TODO appearing in string literals ("TODO" as a status value)
- TODO in markdown files (formatting conflicts with docs-drift scope)
- Template/example paths in documentation

Each was addressed with specific heuristics: string literal detection, `.md` extension exclusion, template path filtering. The philosophy: **every false positive erodes trust, and trust is the product.**

**End of Phase 2: 170 tests, 4 detectors, docs-drift with stale refs + dep drift + LLM comparison.**

## Phase 3: Refinement (Apr 4, Late Afternoon)

After the initial code review pass surfaced 14 findings across docs-drift, the judge, and documentation, Session 4 focused on precision.

### Key improvements

- **Qwen 3.5 reasoning model support** — The LLM judge prompt was updated for Qwen3.5's `think` parameter and f-strings replaced `.format()` to prevent crashes when evidence contained `{` or `}` characters (common in code).
- **7 precision/recall fixes** — Including better code block isolation, more robust dependency name normalization, template path exclusion improvements.
- **Ground truth evaluation test** — A sample repo with a `ground-truth.toml` file annotating expected findings (12 entries: 9 true positives, 3 false positives). The `sentinel eval` command compares scan results against this ground truth and reports precision/recall. Result: **93%+ precision** on the ground truth fixture.
- **Tech debt resolution** — TD-006 (dep-audit scanning the wrong environment) fixed by parsing the target repo's dependency manifest instead of the running Python environment. TD-007 (timestamps lost on DB round-trip) fixed.

### The eval CLI

`sentinel eval <repo-path>` became a first-class command: run all detectors, compare against ground truth, report precision and recall. This closed the loop on ADR-008's evaluation criteria and meant detector quality was measurable, not subjective.

## Phase 4–5: Extended Detectors & GitHub Integration (Apr 4, Evening)

### Schema migrations (resolving TD-003)

Before adding new features that needed schema changes, a migration framework was built: ordered `(version, description, sql)` tuples applied sequentially on database open. Base schema is always v1, migrations are applied in order. First migration (v2): `finding_persistence` table for tracking occurrence counts.

### Finding persistence scoring

Findings that recur across multiple scans get annotated with `occurrence_count`, `first_seen`, and `recurring` flag. The report shows a badge (`♻️ ×3`) for recurring findings. A finding that appears in 3 consecutive scans is more interesting than a new one — persistence is signal.

### Git hotspots detector

A new heuristic detector: run `git log --since=90d --name-only`, count commits per file, flag statistical outliers (files with commits above mean + 2×stdev). High-churn files correlate with higher defect probability. Configurable lookback period, minimum commit threshold, and stdev multiplier.

### GitHub issue creation

The final feature: `sentinel create-issues` takes approved findings and creates GitHub issues. Key design choices:
- **Dedup against existing issues** — Each issue body includes a hidden HTML comment (`<!-- sentinel:fingerprint:xxx -->`) so Sentinel won't create duplicates if run twice
- **Dry-run mode** — Preview what would be created without touching the API
- **Config via environment variables** — `SENTINEL_GITHUB_*` for token/owner/repo, with CLI flag overrides
- **Approval gate** — Only findings explicitly approved via `sentinel approve` become issues

**End of Phase 5: 217 tests, 5 detectors, 6 CLI commands, all vision success criteria met.**

## How It Was Actually Built

### The development tool

Sentinel was built using GitHub Copilot agent mode in VS Code (ADR-006). The builder agent was configured with detailed project instructions, the locked vision, and access to the codebase. The workflow was:

1. Human defines the vision, architecture, constraints, and acceptance criteria
2. Agent implements in ordered slices, running tests after each slice
3. A separate reviewer agent audits the implementation
4. Human makes final decisions on flagged issues

### The autonomous builder pattern

The repo includes a custom `autonomous-builder` agent definition. The agent was given:
- The vision lock (immutable success criteria)
- The phase plan (ordered implementation slices)
- Project conventions (ADRs, open questions tracker, tech debt tracker, glossary)
- A "self-improving workflow" — the agent was expected to update its own instructions based on what worked

Each implementation session followed a loop: read the current state → identify the next slice → implement → test → checkpoint. The `CURRENT-STATE.md` file served as the handoff document between sessions.

### What worked about this approach

- **Docs-first, code-second**: Writing ADRs and the vision lock before any code forced clear thinking about what the system should and shouldn't do. The agent couldn't drift from the vision because the vision was explicit.
- **Ordered slices**: Each implementation slice had clear inputs, outputs, and test criteria. The agent could work autonomously on one slice at a time without needing human guidance mid-slice.
- **Review as separate concern**: Using a dedicated reviewer agent to audit implementation after each phase caught issues the builder missed — prompt injection risks in the judge, edge cases in false positive filtering, documentation drift within the project itself.
- **Checkpoint discipline**: `CURRENT-STATE.md` was updated after every significant milestone, making session boundaries clean. Any session could pick up where the last left off.

### What was hard

- **False positive tuning is empirical**: No amount of upfront design predicted which regex patterns would fire on string literals or template paths. Each false positive required reading the specific failure, understanding why it happened, and adding a targeted heuristic.
- **LLM judge prompt engineering**: Getting a 4B model to reliably return structured JSON (not markdown-wrapped JSON, not partial JSON, not explanations-before-JSON) took several iterations. The `think: false` parameter and explicit "respond ONLY with JSON" instruction were necessary.
- **Evidence containing code**: When the judge evaluates a finding about Python code, the evidence often contains `{` and `}` characters. Python's `.format()` crashed on these. Switching to f-strings fixed it — a small bug with a non-obvious cause.

## Design Principles That Survived Contact with Reality

1. **Precision over breadth** — The system surfaces 5 real issues rather than 20 noisy ones. This was the hardest constraint to hold but the most important.

2. **Deterministic first, LLM second** — The LLM never invents findings. It only evaluates evidence from deterministic tools. This kept the false positive rate manageable.

3. **Everything works without the LLM** — Graceful degradation wasn't just a nice-to-have. During development, Ollama was frequently restarting or pulling models. The system needed to be useful without it.

4. **Evidence-backed or it doesn't ship** — Every finding cites specific code, specific lint output, or specific git history. No "this code looks suspicious" without proof.

5. **Deduplication is a trust feature** — If the same finding appears in every report, the tool is noise. SQLite state, fingerprinting, and suppression exist specifically to prevent this.

## Phase 6–14: The Web UI, Extended Language Support, and Incremental Hardening (Apr 5–6)

After the core product was delivered in a single day, development continued with the autonomous builder running additional sessions. These sessions followed the same checkpoint protocol: read CURRENT-STATE.md, identify the next slice, implement, test, commit.

### Web UI (Sessions 6–10)

A full web interface was built using Flask + htmx — lightweight, server-rendered, no JavaScript build step. Features accumulated across sessions:

- **Finding browser** with filtering by detector, severity, status
- **Bulk triage** — approve/suppress multiple findings at once
- **Run comparison** — diff two scan runs showing new, resolved, and persistent findings
- **Eval history** with SVG trend charts
- **Root-cause pattern clustering** — group findings by automatically detected patterns
- **Finding annotations/notes** — attach context to individual findings

Design choice: htmx over a React SPA. The reasoning was simplicity — no separate build pipeline, no client-side state management, server-side rendering is sufficient for this use case. This aligned with the project's "simple over clever" principle.

### Extended detectors (Sessions 11–15)

- **Complexity detector** — cyclomatic complexity via AST analysis, configurable thresholds
- **ESLint runner** — for TypeScript/JavaScript repos, same shell-out + parse pattern as ruff
- **Go linter** — golangci-lint integration
- **Rust Clippy** — cargo clippy integration
- **Incremental scanning** — only re-scan files modified since the last run (via git diff)

This brought language coverage from Python-only to Python, TypeScript/JS, Go, and Rust. Each detector followed the same pattern: shell out to the ecosystem's native tool, parse structured output, map to Sentinel's `Finding` model.

### Embeddings exploration (Sessions 8–9)

An experimental embedding-based context gatherer was built to replace file-proximity heuristics. This used Ollama's embedding API to find semantically related code for each finding. It worked but was slow and the quality improvement over file-proximity was marginal for the 4B model. Filed as tech debt — the right approach with a stronger model, but premature at current scale.

## Phase 15–17: Production Polish (Apr 6)

### New CLI commands

- **`sentinel init`** — scaffolds a `sentinel.toml` config file in the target repo
- **`sentinel scan-all`** — scans multiple repos from a config file, shared DB for cross-repo dedup
- **`sentinel doctor`** — checks system dependencies (Ollama running? ruff installed? etc.)

These were informed by actually using the tool. `init` reduced the friction of first use. `scan-all` resolved OQ-005 (multi-repo support) by treating it as "run scan in a loop with a shared database" rather than building complex orchestration. `doctor` prevented the most common support question: "why isn't it working?" (Answer: Ollama isn't running.)

### CI and packaging

- GitHub Actions CI testing Python 3.11, 3.12, 3.13
- 90% test coverage tracked with pytest-cov
- Wheel packaging with templates and static files included
- CONTRIBUTING.md for external contributors

## Phase 18: Model Benchmarking (Apr 6)

A direct comparison of Qwen 3.5 4B vs 9B on the same scan:

| Metric | 4B | 9B |
|--------|-----|-----|
| Judge time | 284s | 560s |
| Confirmed findings | — | — |
| Agreement | ~92% overlap |

The 9B model was slower but not meaningfully more accurate on the structured triage task. This validated the 4B default — for binary "is this real?" judgments, the smaller model was sufficient.

Ollama's structured JSON output feature (`format: json`) was also enabled in this session, eliminating JSON parsing failures from the judge. Previously, the model occasionally returned markdown-wrapped JSON or trailing explanations. The format constraint fixed this entirely.

## Phase 19: Real-World Validation (Apr 7)

The most important session for product quality. Sentinel was pointed at **~/wyoclear**, an external Next.js + Python project the tool had never seen.

### Three iterative scans

| Metric | Scan 1 | Scan 2 | Scan 3 |
|--------|--------|--------|--------|
| Findings (after dedup) | 159 | 112 | 104 |
| False positives | 22 | 17 | 12 |
| Judge time | 304s | 276s | 179s |
| Judge inconsistencies | 4 | 4 | 0 |

Each scan-fix-rescan cycle exposed specific FP patterns:

1. **Missing `.next` in skip dirs** — the todo-scanner found 3,836 findings in the Next.js build directory. Fixed by creating `COMMON_SKIP_DIRS` as a single source of truth for all detectors (19 entries: `.next`, `.turbo`, `out`, `coverage`, etc.).
2. **Non-path patterns matched as paths** — Next.js imports like `@/components/foo`, dates like `2026-01-15`, and CSS values were being flagged as broken file references. Fixed with 4 filter stages.
3. **Regex as markdown links** — `[JS](\d+)` in markdown tables parsed as a broken link to file `\d+`. Fixed by detecting regex metacharacters.
4. **Same target, different docs** — Two markdown files referencing the same missing file produced two findings that the judge evaluated inconsistently. Fixed by deduplicating on target path rather than source doc path.
5. **Strikethrough paths** — `~~old/path/deleted.tsx~~` was flagged as a broken reference. The path was intentionally documenting a deletion. Fixed by detecting strikethrough syntax.

### The key lesson: LLM judges fabricate reasoning

In Scan 1, the judge confirmed 42 out of 42 obvious non-path patterns (dates, URLs, CSS values) with fabricated but plausible-sounding reasoning like "the referenced file `2026-01-15` appears to be missing from the repository." The 4B model would dutifully construct an explanation for why any input was a real issue.

This proved a core architectural thesis: **detector precision must be high before the LLM sees anything.** The judge is a refinement layer for genuinely ambiguous cases, not a noise filter. Adding deterministic FP filters reduced findings by 35% and FPs by 45% — far more effective than any prompt engineering could achieve.

## Phase 20: Strategic Recalibration (Apr 7)

After 19 implementation sessions, a docs-only session stepped back to evaluate what had actually been built versus what was promised.

### The honest assessment

Most of Sentinel's detectors (lint runner, todo scanner, complexity) were wrappers around tools developers already have. They added value through unified reporting and dedup, but a developer with `ruff` and `grep` already has 80% of that capability.

The **genuinely differentiated** capability was **cross-artifact analysis** — specifically, docs-drift detection. No existing tool compares documentation against code to find semantic inconsistencies. The stale-reference detector (100% accuracy across 56 findings on wyoclear) was finding real issues that no combination of existing tools would catch.

### Vision Lock v3.0

This led to VISION-LOCK v3.0 — a strategic rewrite positioning cross-artifact analysis as the core differentiator:

- **Core concept reframed**: The LLM has two roles — judge (shipped, validates findings) and analyst (planned, discovers cross-artifact inconsistencies)
- **Detector value tiers**: lint/todo/complexity are "low" (wrap existing tools), docs-drift is "high" (unique capability), planned semantic detectors are "highest" (the real product)
- **Key product insight**: Even a binary "in sync / needs review" signal is high value. A 4B model can't explain HOW docs are wrong, but reliably identifying THAT they need review is the product.
- **New success criterion**: "surface issues the dev didn't already know about" — partially met

### What this means for development priority

New investment should go to cross-artifact semantic detectors (docs-drift with code comprehension, test-code coherence) rather than improving lint wrappers. The existing low-value detectors are kept — they're cheap to maintain and useful for repos that don't have ruff set up — but they're not the product.

## The Template Extraction (Apr 7)

After 20 sessions of autonomous development, the workflow itself had matured into a reusable pattern. The `.github/` directory contained a battle-tested configuration:

- An **autonomous builder agent** with checkpoint protocol, authority ordering, and self-improving workflow
- A **reviewer subagent** (read-only tools, structured output, handoff to fix)
- A **planner subagent** (read-only tools, handoff to implementation plan)
- **7 dev-cycle prompts** encoding the full workflow: plan → implement → review → complete
- Documentation skeleton with vision lock, ADRs, open questions, tech debt, and glossary
- Cross-session continuity via CURRENT-STATE.md and repository memory

This was extracted into a standalone **[copier](https://copier.readthedocs.io/) template** (`~/copilot-autonomous-template/`) that can bootstrap the same autonomous workflow in any new Git repo. The template accepts variables (project name, description, language, author) and generates all 27 files with correct substitution.

Usage: `copier copy ~/copilot-autonomous-template new-project` — then open in VS Code, select the autonomous-builder agent, and tell it to start Phase 0.

The extraction validated a hypothesis from ADR-006: **the Copilot agent configuration is itself a reusable artifact**, not just project-specific scaffolding. The workflow — vision lock → checkpoint protocol → ordered slices → reviewer passes → durable state — transfers to any project.

## What's Left

The core product is complete and validated on external repos. What remains is strategic:

- **Semantic docs-drift detector** (OQ-008) — pair doc sections with code sections using embeddings, ask the LLM for binary "in sync / needs review" verdicts. This is the highest-value planned feature.
- **Test-code coherence detector** (OQ-009) — detect when test files don't cover recently changed code paths. Unknown whether the 4B model can reliably deliver this.
- **Dead code / unused exports** — tree-sitter based, deterministic, cross-file analysis
- **PyPI publication** — ✅ Published as `repo-sentinel` on PyPI
- **Real-world validation on Go/Rust repos** — detectors exist but haven't been battle-tested outside unit tests

The system scans repos, produces useful morning reports, creates GitHub issues after human approval, and — most importantly — finds cross-artifact issues that no other tool catches. The autonomous development workflow that built it is now a reusable template.

## Phase 10: Depth Over Breadth (Apr 9)

After a strategic pause, work resumed with a focus on making the existing system more capable and measurable rather than adding new features.

### TD-012: Git-Hotspots Enrichment

The git-hotspots detector was flagging files with high churn but providing no insight into *why* the churn mattered. A file touched 30 times could be under active development (fine) or a chronic bug target (concerning). The detector now classifies commit messages into categories:

- **fix/bugfix**: `fix`, `bug`, `patch`, `hotfix`, `resolve`, `repair` — and their common misspellings
- **refactor**: `refactor`, `restructure`, `reorganize`, `rename`, `simplify`, `cleanup`
- **feature**: `feat`, `feature`, `implement`, `introduce`, `support`

When a file has 15+ commits with >50% classified as bug fixes, severity escalates from LOW to MEDIUM — signaling a chronic problem area rather than routine development. The enrichment adds author count summaries and dominant commit-type context to each finding.

Initial regex patterns were too aggressive — `error`, `issue`, `move`, `add`, `new` all caused false classification. The code review caught this and the patterns were tightened to conservative terms only.

### OQ-012: Per-Detector Model Providers

A long-standing open question: should different detectors use different models? The docs-drift detector works fine with a 4B model, but the semantic analysis detectors might benefit from larger models without slowing down the entire pipeline.

The solution: a `[sentinel.detector_providers]` config section in `sentinel.toml`:

```toml
[sentinel.detector_providers.semantic-drift]
provider = "openai"
model = "gpt-4o-mini"
api_base = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model_capability = "advanced"
```

Each detector can have its own provider, model, and capability tier. Fields not specified inherit from the global config. The runner swaps the provider in the context before each detector runs and restores it afterward — using `try/finally` to prevent provider leaks if a detector crashes.

This was recorded as ADR-013.

### The Code Review That Mattered

Running the reviewer subagent after the TD-012 + OQ-012 slice caught a critical bug: the runner's provider restore wasn't exception-safe. If a detector with a per-detector provider raised an exception, the override provider would leak to all subsequent detectors. Five other issues were caught and fixed in the same pass.

**Key lesson reinforced**: The reviewer subagent pays for itself. The bugs it catches are exactly the kind that surface in production months later as mysterious behavior changes — "why is detector X using the wrong model?"

### Benchmarking System

The project had no way to measure detector performance across models or track it over time. Three components were built:

1. **`sentinel benchmark <repo>`** — a CLI command that runs all detectors with timing, produces per-detector stats, and evaluates against ground truth when available
2. **TOML output format** — human-readable, machine-parseable results saved to `benchmarks/`
3. **`--compare` mode** — side-by-side markdown tables comparing multiple benchmark runs

First benchmark results on the sample-repo fixture: **32 findings, 100% precision, 100% recall** (deterministic only). Against tsgbuilder (a real Flask web app): 134 findings across 7 active detectors in 14 seconds.

The reviewer caught TOML string injection (unescaped quotes in file paths would produce invalid TOML) and lossy eval serialization (list data was silently converted to counts). Both were fixed.

### Sample Repo Expansion

The test fixture exercised only 4 of 14 detectors. Added:

- **`processing.py`**: A deliberately complex function (CC=21, 76 lines) and a long function (65 lines) for the complexity detector
- **`.env.example`**: 4 stale vars + 1 undocumented var for the stale-env detector
- **`config.py` updates**: `os.getenv`/`os.environ.get` calls to exercise stale-env's cross-reference logic

Ground truth expanded from 17 to 30 expected findings, now covering complexity, stale-env, unused-deps, dead-code, docs-drift, lint-runner, and todo-scanner — **7 of 14 detectors** (was 4/14).

### The Numbers

| Metric | Session 20 (Apr 7) | Current (Apr 9) |
|--------|---------------------|------------------|
| Tests passing | 630 | 971 |
| Detectors | 14 | 14 |
| Ground truth coverage | 4/14 detectors | 7/14 detectors |
| Sample repo findings | 17 expected | 30 expected |
| ADRs | 12 | 13 |
| Git commits | 155 | ~163 |
| Benchmark results tracked | 0 | 2 (sample-repo, tsgbuilder) |

### What this session proved

1. **The reviewer-first workflow works.** Three review-fix cycles across this session caught real bugs (exception safety, injection, lossy data) before they could ossify.
2. **Benchmarking enables data-driven decisions.** Now we can measure whether switching from qwen3.5:4b to a larger model actually improves recall — not just hope it does.
3. **Fixture expansion is high-leverage testing work.** Going from 4/14 to 7/14 detectors covered by ground truth means future changes to the eval system or detector pipeline have much broader regression coverage.
