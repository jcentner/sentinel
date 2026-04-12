# ADR-011: Capability tier system for detectors

**Status**: Superseded by ADR-016
**Date**: 2026-04-08 (amended 2026-04-10)
**Deciders**: Autonomous builder (Session 28–29), human + autonomous builder (Session 33)

## Context

ADR-010 introduced pluggable model providers, enabling users with more powerful models (cloud or larger local) to get richer analysis. However, no mechanism existed to:

1. Declare what model capability a detector requires to function well.
2. Warn users when their configured model may be underpowered for a detector.
3. Allow detectors to adapt their behavior based on model capability (e.g., simpler prompts for weaker models, structured analysis for stronger ones).

Without this, all LLM-assisted detectors behaved identically regardless of whether the model was a 4B local model or a frontier cloud model — wasting the potential of more capable models and producing potentially low-quality results from underpowered ones.

### Amendment context (Session 33)

The original tier table mapped models to tiers based on parameter count (e.g., "8B → standard"). Real-world benchmarking (Sessions 31–33) demonstrated this was inaccurate:

- **qwen3.5:4b** and **qwen3.5:9b** score ≈27 and ≈32 on independent aggregate rankings — the same empirical class.
- **gpt-5.4-nano** scores ≈38–44 — a significant quality jump above both local models.
- The test-coherence detector shows ~40% FP rate at 4B, ~30% at 9B, and ~15% at cloud-nano. The basic→standard boundary is this quality jump, not a parameter count threshold.

Tier-to-model mapping must be empirical, not assumed from parameter count.

## Decision

Introduce a `CapabilityTier` enum with four levels:

| Tier | Value | Empirical model class | Expected behavior |
|------|-------|-----------------------|-------------------|
| `NONE` | `"none"` | — | Detector needs no model (deterministic/heuristic) |
| `BASIC` | `"basic"` | 4B local, 9B local (same empirical class) | Binary signal: "needs review" / "in sync" |
| `STANDARD` | `"standard"` | Cloud-nano (gpt-5.4-nano) and above | Enhanced prompts, structured category analysis |
| `ADVANCED` | `"advanced"` | Cloud-small (gpt-5.4-mini, Haiku 4.5) and frontier | Full explanatory analysis, multi-step reasoning |

### Tier boundary rationale

- **basic**: Models scoring ≈25–35 on aggregate benchmarks. Sufficient for binary classification prompts. Both 4B and 9B local models fall here because the quality difference between them (~5 points) is within the same capability class.
- **standard**: Models scoring ≈38–44. The jump from 9B-local (~32) to cloud-nano (~38–44) is the critical quality boundary — it's where structured reasoning and lower false-positive rates become achievable. This is measured, not assumed.
- **advanced**: Models scoring ≈45+. Cloud-small (gpt-5.4-mini ≈38–49, Haiku 4.5 ≈31–37) and frontier models. Full multi-step reasoning and explanatory analysis.

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
- Tier boundaries are grounded in measured quality data, not parameter count assumptions.

**Negative**:
- Adds a new configuration knob that users need to understand.
- Detector authors must reason about which tier their detector targets.
- Tier boundaries may shift as new models are released — requires periodic re-evaluation.

**Neutral**:
- The tier is advisory — the runner never prevents a detector from running. This avoids false-exclusion failure modes at the cost of potentially degraded results from underpowered models.

## References

- ADR-010: Pluggable model provider interface
- `src/sentinel/models.py`: `CapabilityTier` enum definition
- `src/sentinel/detectors/base.py`: `capability_tier` property on `Detector` ABC
- `src/sentinel/core/runner.py`: Tier comparison and warning logic
- `src/sentinel/core/compatibility.py`: Authoritative compatibility matrix data
- `docs/reference/compatibility-matrix.md`: User-facing compatibility documentation
- `docs/reference/model-benchmarks.md`: Empirical benchmark data backing tier decisions
