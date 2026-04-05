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
| Apr 5 | Final code review pass, 220 tests passing |

**Total wall-clock from first code commit to feature-complete: ~12 hours across one day.**

## The Numbers

| Metric | Value |
|--------|-------|
| Source code (Python) | ~3,600 lines across 25 files |
| Test code | ~3,100 lines across 23 files |
| Tests passing | 220 |
| Detectors | 5 |
| CLI commands | 6 |
| ADRs written | 8 |
| Documentation files | 26 markdown files |
| Git commits | 46 |
| External runtime dependencies | 2 (click, httpx) |

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

## What's Left

The core product is complete. What remains is incremental:

- **3 deferred detectors**: SQL anti-patterns, Semgrep integration, complexity/dead-code heuristics
- **Context gatherer upgrade**: Replace file-proximity with embedding-based retrieval (needs vector store decision)
- **Async detectors**: Current detectors run sequentially; parallelism would improve scan speed
- **Minor polish**: Config type validation, markdown TODO visibility, Poetry pyproject.toml support

None of these block the core value proposition. The system scans a repo, produces a useful morning report, and creates GitHub issues after human approval. That's what was promised, and that's what was delivered.
