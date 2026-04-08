# Strategy

## Core concept

Local Repo Sentinel is a narrow, practical agent for software repositories. It runs on a local development machine, watches a codebase over time, collects evidence from the repo and its surrounding artifacts, and produces a concise morning report of likely issues worth a human reviewing. After approval, it can turn selected findings into GitHub issues.

The goal is not autonomous coding. The goal is disciplined, evidence-backed issue triage.

## Why this exists

Most developer-facing AI tools focus on helping in the moment: autocomplete, chat, inline edits, code generation, or agentic implementation. That leaves a gap for a different kind of assistant — one that works in the background, revisits a repository with fresh context, and surfaces issues that are easy to miss during normal feature work.

This is especially relevant for someone already working deeply with AI-assisted development, who wants something complementary rather than redundant. In a workflow that already includes VS Code, GitHub Copilot, multiple projects, and consulting/client work, the value is not another chat box. The value is a local system that quietly reviews the repo overnight and hands back a prioritized set of observations in the morning.

## Target user

A developer working primarily on Windows 11 with WSL 2 Ubuntu, using 8 GB VRAM GPUs (RTX 3070 Ti desktop, RTX 5070 laptop), comfortable connecting local models for retrieval-oriented support tasks like embeddings and reranking. Works across multiple projects including a primary role and consulting/client engagements.

## What it should be good at

- **Cross-artifact inconsistency detection**: Identifying when docs, tests, config, and dependencies drift out of sync with the code. This is the core differentiator — no existing tool does this.
- Surfacing evidence-backed candidates for bugs or maintenance issues
- Detecting broken links and stale path references in documentation
- Clustering similar findings to avoid noisy repetition
- Turning raw observations into clear issue drafts for human approval
- Maintaining continuity across repeated runs (deduplication, recurrence tracking)
- Providing a binary "needs review" triage signal: identifying *that* something is out of sync, even if the model can't fully explain *how* to fix it

### Detector value tiers (honest assessment)

Based on real-world validation (104 findings, 88% confirmation rate):

| Tier | What | Capability Tier | Why |
|------|------|----------------|-----|
| **Highest value (planned)** | Semantic docs-drift, test-code coherence | basic–standard | Cross-artifact analysis that nothing else does. Even a binary signal is high value. Stronger models unlock structured explanations. |
| **High value (shipped)** | Docs-drift (broken links, stale paths) | none (deterministic) | Catches real drift that accumulates silently. 97% accuracy. |
| **Medium** | Complexity | none (deterministic) | Useful on first scan; diminishing on repeat runs. |
| **Low** | Lint, ESLint, go-linter, rust-clippy, todo-scanner | none (deterministic) | Duplicate what dev toolchains already provide. Useful only for repos without CI linting. |
| **Mixed** | git-hotspots, dep-audit | none (deterministic) | Statistics without insight; or useful only if user doesn't already run audit tools. |

New development investment should focus on the top two tiers. More powerful models (via cloud providers or larger local GPUs) unlock a new dimension: detectors that don't just flag *that* something is wrong, but explain *what* is wrong and *why*.

## What it should not pretend to do

- Substitute for senior code review or architecture review
- Implement fixes or plan large refactors
- Make architectural decisions
- Act without approval
- Flood GitHub with speculative issues

The credibility of the project depends on staying narrow and honest about this boundary.

## Why local-first execution matters

Running locally *by default* changes the value proposition:

- **Privacy**: Code never leaves the machine unless you explicitly configure a cloud provider. Critical for client/consulting repos.
- **Low marginal cost**: After hardware investment, each run with local models is essentially free.
- **Offline iteration**: Works without internet, doesn't depend on API availability.
- **Natural fit**: Integrates into existing WSL 2 / VS Code / Ollama workflows.

For users who want more powerful models — Azure OpenAI, OpenAI direct, or any OpenAI-compatible endpoint — the provider is pluggable. This is an explicit opt-in with a clear tradeoff: more model capability in exchange for sending code excerpts to a cloud API. Sentinel does not make that choice for the user; it makes the choice easy to configure.

The default experience remains fully local. No account, no API key, no internet required.

## Primary output

1. **Morning report**: Concise, reviewable, organized around a shortlist of findings worth attention. Scannable in under 2 minutes — one line per finding, expandable evidence, clear severity tags.
2. **Draft GitHub issues**: Created only after explicit human approval.

That keeps the human firmly in control while still making the system materially useful.

## Why it is worth building

1. **Daily usefulness**: It can become part of a real development workflow, not a demo.
2. **Credible scope for local models**: It asks a small model to judge and summarize evidence, not to autonomously engineer solutions. And for users with more powerful models, it asks harder questions.
3. **Extensibility as a feature**: Pluggable detectors and pluggable model providers mean every user makes Sentinel what they need. A privacy-conscious consultant runs Ollama locally. A team with Azure credits runs GPT-5.4-nano for deeper analysis. Both use the same pipeline.
4. **Writeup and open-source value**: Specific enough to explain clearly, evaluate honestly, and publish without sounding like generic agent hype.

## Relationship to existing coding assistants

This is not a replacement for interactive coding tools like GitHub Copilot or other chat-based assistants. Those tools help while coding. Repo Sentinel helps when stepping back.

Interactive tools optimize for speed in the current task. Repo Sentinel optimizes for persistence, reviewability, and surfacing overlooked issues across the repository as a whole.

It is also not a replacement for linters, security auditors, or complexity analyzers — those tools already exist and most dev teams already run them. The current suite of deterministic detectors (lint, complexity, todo, dep-audit) provides utility for repos without those tools, but **the strategic differentiator is cross-artifact semantic analysis**: comparing docs vs code, tests vs implementation, and config vs usage to find drift that no existing tool catches.

## Why extensibility matters

Sentinel's value compounds when users can shape it to their context:

- **Model provider extensibility**: A `ModelProvider` protocol lets users swap between Ollama (local, free, private) and OpenAI-compatible APIs (Azure OpenAI, OpenAI, vLLM, LM Studio). The pipeline doesn't care where the model lives. See [ADR-010](../architecture/decisions/010-pluggable-model-provider.md).
- **Detector extensibility**: Custom detectors can be loaded from an external directory via `detectors_dir` config. Adding a detector is a single Python file with a `detect()` method — no core changes required.
- **Capability-tiered detectors**: Detectors declare what model class they need (`basic`, `standard`, `advanced`). Users with a 4B local model get binary triage signals. Users with a 9B or cloud model get structured analysis. Everyone uses the same pipeline.

The design philosophy is **opinionated defaults, extensible everything**: works out of the box with Ollama and sensible defaults, but every major axis is configurable.
