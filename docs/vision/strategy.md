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

- Surfacing evidence-backed candidates for bugs or maintenance issues
- Detecting inconsistencies between code, tests, docs, and configuration (docs drift)
- Summarizing suspicious patterns across code, tests, docs, and configuration
- Clustering similar findings to avoid noisy repetition
- Turning raw observations into clear issue drafts for human approval
- Maintaining continuity across repeated runs

## What it should not pretend to do

- Substitute for senior code review or architecture review
- Implement fixes or plan large refactors
- Make architectural decisions
- Act without approval
- Flood GitHub with speculative issues

The credibility of the project depends on staying narrow and honest about this boundary.

## Why local execution matters

Running locally changes the value proposition:

- **Privacy**: Code never leaves the machine. Critical for client/consulting repos.
- **Low marginal cost**: After hardware investment, each run is essentially free.
- **Offline iteration**: Works without internet, doesn't depend on API availability.
- **Natural fit**: Integrates into existing WSL 2 / VS Code / Ollama workflows.

It also makes the project more interesting than a generic cloud-based code review wrapper. The point is to show what a small local model can do when paired with a well-bounded problem, repeated runs, and strong evidence gathering.

## Primary output

1. **Morning report**: Concise, reviewable, organized around a shortlist of findings worth attention. Scannable in under 2 minutes — one line per finding, expandable evidence, clear severity tags.
2. **Draft GitHub issues**: Created only after explicit human approval.

That keeps the human firmly in control while still making the system materially useful.

## Why it is worth building

1. **Daily usefulness**: It can become part of a real development workflow, not a demo.
2. **Credible scope for local models**: It asks a small model to judge and summarize evidence, not to autonomously engineer solutions.
3. **Writeup and open-source value**: Specific enough to explain clearly, evaluate honestly, and publish without sounding like generic agent hype.

## Relationship to existing coding assistants

This is not a replacement for interactive coding tools like GitHub Copilot or other chat-based assistants. Those tools help while coding. Repo Sentinel helps when stepping back.

Interactive tools optimize for speed in the current task. Repo Sentinel optimizes for persistence, reviewability, and surfacing overlooked issues across the repository as a whole.
