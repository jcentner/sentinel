# ADR-003: Model-agnostic design via Ollama

**Status**: Accepted
**Date**: 2026-03-28
**Deciders**: Project founder

## Context

The initial model choice is Qwen3.5 4B, identified as the best 8GB-friendly local model as of March 2026. However, model rankings shift every few months. The system should not be tightly coupled to any specific model.

## Decision

All model interaction goes through the Ollama API. The system is model-agnostic — model names are configuration, not code. Prompts are written for general instruction-following models, not Qwen-specific features.

The value of the system comes from the **pipeline** (deterministic detectors + retrieval + LLM judgment + human approval), not the model's raw intelligence. If the model changes, the pipeline still works.

## Consequences

**Positive**:
- Swap models by changing a config value, not code
- Resilient to model churn in the small-model space
- Makes a more defensible engineering argument in writeups
- Supports future option of pointing at a hosted API-compatible endpoint

**Negative**:
- Can't exploit model-specific features (e.g., Qwen's tool-use format)
- May leave some model-specific performance on the table
- Ollama becomes a hard dependency (though it's well-established)

## Alternatives considered

- **Direct model loading (llama.cpp, vLLM)**: More control but more complexity. Ollama already handles quantization, context management, and API.
- **Multiple backend support**: Supporting both Ollama and direct loading adds complexity without clear benefit at MVP stage.
