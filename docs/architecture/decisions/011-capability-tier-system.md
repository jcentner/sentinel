# ADR-011: Capability tier system for detectors

**Status**: Accepted
**Date**: 2026-04-08
**Deciders**: Autonomous builder (Session 28–29)

## Context

ADR-010 introduced pluggable model providers, enabling users with more powerful models (cloud or larger local) to get richer analysis. However, no mechanism existed to:

1. Declare what model capability a detector requires to function well.
2. Warn users when their configured model may be underpowered for a detector.
3. Allow detectors to adapt their behavior based on model capability (e.g., simpler prompts for weaker models, structured analysis for stronger ones).

Without this, all LLM-assisted detectors behaved identically regardless of whether the model was a 4B local model or a frontier cloud model — wasting the potential of more capable models and producing potentially low-quality results from underpowered ones.

## Decision

Introduce a `CapabilityTier` enum with four levels:

| Tier | Value | Typical models | Expected behavior |
|------|-------|----------------|-------------------|
| `NONE` | `"none"` | — | Detector needs no model (deterministic/heuristic) |
| `BASIC` | `"basic"` | Qwen3.5 4B, Phi-3 mini | Binary signal: "needs review" / "in sync" |
| `STANDARD` | `"standard"` | Qwen3.5 8B, GPT-5.4-nano | Enhanced prompts, structured category analysis |
| `ADVANCED` | `"advanced"` | GPT-5.4-mini, Claude Haiku 4.5 | Full explanatory analysis, multi-step reasoning |

### How it works

1. **Config**: Users set `model_capability = "basic"` (default) in `sentinel.toml`.
2. **Detectors**: Each detector declares a `capability_tier` property (default: `NONE`).
3. **Runner**: At scan time, the runner compares each detector's required tier against the configured tier. If the detector requires a higher tier, it logs a warning but still runs — the tier is informational, not a gate.
4. **Adaptive behavior**: LLM-assisted detectors (semantic-drift, test-coherence) check the capability tier and use enhanced prompts/larger context windows when `STANDARD` or `ADVANCED` is available.

### Error handling

Invalid `model_capability` values are caught at two levels:
- `config.py`: Validates against an allowlist during TOML loading.
- `runner.py`: Wraps `CapabilityTier()` construction in try/except with fallback to `BASIC`.

## Consequences

**Positive**:
- Users with more powerful models get richer analysis automatically.
- Users with small local models aren't penalized — basic behavior is the default.
- Detectors can evolve to support multiple capability levels independently.
- Warnings surface configuration mismatches without blocking scans.

**Negative**:
- Adds a new configuration knob that users need to understand.
- Detector authors must reason about which tier their detector targets.

**Neutral**:
- The tier is advisory — the runner never prevents a detector from running. This avoids false-exclusion failure modes at the cost of potentially degraded results from underpowered models.

## References

- ADR-010: Pluggable model provider interface
- `src/sentinel/models.py`: `CapabilityTier` enum definition
- `src/sentinel/detectors/base.py`: `capability_tier` property on `Detector` ABC
- `src/sentinel/core/runner.py`: Tier comparison and warning logic
