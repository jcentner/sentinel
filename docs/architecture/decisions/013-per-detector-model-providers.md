# ADR-013: Per-Detector Model Provider Configuration

**Status**: Accepted
**Date**: 2026-04-09
**Deciders**: Jacob Centner

## Context

Different detectors have different model requirements. Deterministic detectors don't need a model at all. Semantic detectors (semantic-drift, test-coherence) benefit from more capable models. A user with Ollama running locally might want to route expensive semantic detectors to Azure OpenAI while keeping the judge on the local model.

Previously, a single global `provider`/`model` pair was used for all LLM calls in a scan. Users who wanted more powerful analysis for specific detectors had to change the global config and accept the cost for all LLM calls, not just the ones that benefit from it.

## Decision

Add per-detector provider overrides via `[sentinel.detector_providers.<name>]` config sections.

### Config shape

```toml
[sentinel]
provider = "ollama"
model = "qwen3.5:4b"

[sentinel.detector_providers.semantic-drift]
provider = "azure"
model = "gpt-5.4-nano"
api_base = "https://myresource.services.ai.azure.com"
model_capability = "standard"

[sentinel.detector_providers.test-coherence]
model = "llama3:8b"
```

### Inheritance rules

- Any field left empty (or omitted) inherits from the global config
- If the resolved per-detector config is identical to the global config, no new provider is created
- Provider instances are cached by the runner to avoid duplicate connections

### Scope

- Per-detector providers apply only to the **detection phase** (when `context.config["provider"]` is read by LLM-assisted detectors)
- The **judge** and **synthesis** steps always use the global provider
- This is intentional: the judge evaluates all findings uniformly, regardless of which model produced them

## Consequences

- Users can run cheap local models for basic detectors and expensive cloud models for advanced detectors in a single scan
- Config complexity increases but is opt-in — the default behavior is unchanged
- The `ProviderOverride` dataclass validates per-detector config at load time
- `model_capability` can be overridden per-detector, allowing capability tier matching per model

## Alternatives considered

1. **Two-tier approach** (local provider + cloud provider): Simpler but less flexible. Doesn't handle three or more providers.
2. **Per-detector config in detector code**: Detectors declare their preferred provider. Rejected — provider choice is a user decision, not a detector decision.
