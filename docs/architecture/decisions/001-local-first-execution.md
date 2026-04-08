# ADR-001: Local-first execution model

**Status**: Accepted
**Date**: 2026-03-28
**Deciders**: Project founder

## Context

Most AI code review tools are cloud-hosted (PR-Guardian-AI, various GitHub Actions bots) or depend on hosted API calls (night-watch-cli uses Claude CLI / Codex). Local Repo Sentinel needs to decide whether to be cloud-first, API-first, or local-first.

The target user works with client repositories where code privacy matters, wants low marginal cost per run, needs offline capability, and already has 8 GB VRAM GPUs available.

## Decision

Sentinel runs entirely locally. All model inference, embedding, reranking, state storage, and report generation happen on the user's machine. The only external call is the optional GitHub API for issue creation after explicit approval.

## Consequences

**Positive**:
- Code never leaves the machine — critical for client/consulting repos
- Zero marginal cost per run after hardware investment
- Works offline
- Natural fit into existing WSL 2 / Ollama dev workflows
- More interesting open-source pitch than "another cloud API wrapper"

**Negative**:
- Limited by local hardware (8 GB VRAM constrains model size to ~4B parameters)
- Model quality ceiling is lower than frontier hosted models
- User responsible for model setup, updates, Ollama management

**Neutral**:
- Architecture should still support a "remote inference" mode in the future (e.g., calling a hosted API instead of Ollama), but this is not a priority
- → See [ADR-010](010-pluggable-model-provider.md) for the provider abstraction that enables remote inference as an opt-in.

## Alternatives considered

- **Cloud API (e.g., Anthropic, OpenAI)**: Better model quality, but adds cost per run, requires internet, sends code to third parties. Rejected for privacy and cost reasons.
- **Hybrid (local detectors, cloud LLM)**: Reasonable compromise, but adds complexity and a hard dependency. Could be a future option.
