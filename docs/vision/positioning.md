# Positioning & Differentiation

## Framing

**A local, evidence-backed repository issue triage system for overnight code health monitoring.**

That framing is narrower than "AI code reviewer" and more honest than "autonomous software engineer." That is a strength, not a limitation.

## Not

- "AI code reviewer" — implies human-level judgment we can't deliver from a 4B model
- "Autonomous repo engineer" — we explicitly don't implement fixes
- "Copilot replacement" — we complement interactive tools, not compete

## Instead

- "Local evidence-backed repo issue triage"
- "Overnight code health monitor for WSL dev workflows"
- "Small-model repo sentinel using deterministic detectors + LLM judgment"

## Competitive landscape (March 2026)

### PR-time reviewers (triggered by diffs, not standing health)

- **jstar-code-review**: Local-first AI code review with 2-stage triage, documentation drift detection, deterministic security audit. Tags: `documentation-drift`. Closest feature overlap with our docs-drift ambitions, but it's PR-scoped, not persistent.
- **PR-Guardian-AI**: AI-powered PR review via webhooks + FastAPI. Cloud-oriented.
- **reviewd**: Local AI PR reviewer for GitHub/BitBucket. Terminal-based.

### Autonomous executors (take specs/PRDs and implement code)

- **night-watch-cli**: Overnight PRD execution for AI-native devs. Runs Claude CLI or Codex in isolated git worktrees, opens pull requests while you're offline. Recently added "create board issues from audit findings." This is the closest competitor in the "overnight" space, but fundamentally tries to write code and open PRs.

### Static analysis tools (deterministic, no LLM)

- **SQLFluff**: SQL linter (9.6k stars). Multi-dialect, extensible rules. We should consume it as a detector, not replicate it.
- **Semgrep**: Multi-language static analysis. Pattern-based. Excellent as an upstream detector.
- **ast-grep**: Structural code search/lint via tree-sitter. Fast, portable.
- **ruff**: Python linter/formatter. Consume as detector for Python repos.

### Documentation testing (narrow, mostly markdown-focused)

- **mdproof**: Turn markdown docs into executable tests. Narrow.
- **zero-context-validation**: Claude skill for testing doc completeness. Concept overlap.

## Where Sentinel sits

Sentinel occupies a real gap: **persistent, scheduled observation with human-gated issue creation**. No existing tool combines:

1. Scheduled/overnight runs (not PR-triggered)
2. Deterministic detectors + LLM judgment layer
3. Cross-artifact consistency checking (code ↔ docs ↔ tests ↔ config)
4. Persistent state for deduplication and false-positive suppression
5. Human approval gate before any external action
6. Fully local execution on consumer hardware

The nearest competitor (night-watch-cli) is fundamentally an execution agent that writes code overnight. Sentinel is fundamentally an observation agent that surfaces issues for humans.

## The one trap to avoid

Do not optimize for "agentic." Optimize for precision.

A mediocre local agent that opens three good issues per week is useful. A flashy one that opens twenty vague issues is dead on arrival.
