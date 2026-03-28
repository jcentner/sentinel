# Critical Review

> Captured from the initial design review session (2026-03-28). This is an expert critical analysis of the brainstorm document, informed by competitive research and the full conversation context.

## What the brainstorm gets right

The positioning is strong. "Evidence-backed issue triage" is a defensible, narrow claim that avoids the credibility trap of calling it an "AI code reviewer." The explicit non-goals (no fixes, no architecture plans, no PRs, no autonomous action) are the best part of the document — they show discipline and will make the writeup honest.

The complementarity argument (this helps when *stepping back*, not when coding) is genuinely differentiated. Most tools in this space are either:
- **PR-time reviewers** (jstar-code-review, PR-Guardian-AI, reviewd) — triggered by diffs, not by standing repo health
- **Autonomous executors** (night-watch-cli) — which take specs/PRDs and *implement* code, opening PRs overnight

Sentinel occupies a real gap: **persistent, scheduled observation with human-gated issue creation**.

## What was missing or undercooked

### 1. The detector architecture was vague

The brainstorm said "runs analyzers/tests/checks" and "detectors generate candidates" but didn't define *what kind* of detectors. There are three tiers:

- **Deterministic**: Lint output, test failures, TODO/FIXME scans, dependency audit, SQLFluff, Semgrep rules. Cheap, reliable, no model needed.
- **Heuristic**: Git-history hotspots, churn rate, complexity metrics, dead-code analysis via tree-sitter. Also model-free.
- **LLM-assisted**: Model reads code + context and judges. Where the model earns its keep, but also where false positives live.

**Resolution**: The MVP should be mostly deterministic + heuristic, with the LLM as the judgment/summarization layer, not the primary signal source. → See [ADR-002](../architecture/decisions/002-deterministic-detectors-first.md).

### 2. Docs consistency was a missing first-class use case

Docs-to-docs and docs-to-code consistency checking is one of the best use cases for a small local model because:
- It's a **comparison task** (do these agree?), not open-ended generation
- Evidence is concrete (README says X, code does Y)
- Humans chronically neglect it and existing linters can't catch it
- Scales naturally across the repo

**Resolution**: Docs-drift is now a named, first-class detector category. → See [ADR-005](../architecture/decisions/005-docs-drift-first-class-detector.md).

### 3. The "overnight" framing hid an architecture question

"Overnight" implies cron-style batch, but the brainstorm didn't address: What triggers a run? What's the scope per run? Where does state live?

**Resolution**: Multiple trigger modes (cron, git hook, manual, watch). Scope options (full, incremental, targeted). SQLite state from day one. → See [ADR-004](../architecture/decisions/004-sqlite-state-from-day-one.md).

### 4. The Qwen 3.5 4B dependency is a bet, not a given

Model rankings shift every few months. The architecture should be model-agnostic from day one.

**Resolution**: Model-agnostic via Ollama. The system's value comes from the pipeline, not the model. → See [ADR-003](../architecture/decisions/003-model-agnostic-via-ollama.md).

### 5. SQL/query anti-patterns are feasible but scoped

Detecting queries that should use CTEs is interesting but secondary:
- SQLFluff (9.6k stars) handles SQL *style* linting — consume it, don't replicate it
- Semantic anti-patterns (CTE suggestions, N+1 across files) are where an LLM adds value
- If target repos are primarily TypeScript, SQL anti-patterns are Phase 2

**Resolution**: Logged as [OQ-006](../reference/open-questions.md) — build as pluggable detector wrapping SQLFluff + LLM prompt.

### 6. No eval criteria defined

Without measurable criteria, we can't evaluate whether Sentinel works or write an honest writeup.

**Resolution**: Logged as [OQ-007](../reference/open-questions.md) — define precision@k, false positive rate, time-to-review before coding.

## Honest concerns

**False-positive rate is the hardest thing to get right.** A system that produces 20 findings and reduces to 3 real ones is useful. A system with 20 findings of which 15 are noise is dead. This is an empirical problem — plan for aggressive tuning.

**The morning report UX needs to be actually good.** Scannable in under 2 minutes. One line per finding, expandable evidence, clear severity tags. If reviewing the report takes longer than manually scanning the repo, no one will use it.

## Bottom line

The concept is sound and well-positioned. The main risk isn't the idea — it's building something too broad too early and drowning in false positives. Ship a tight MVP with 3-4 deterministic detectors, docs-drift checking, LLM-as-judge, and a good morning report format.
