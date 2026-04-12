# ADR-016: Benchmark-driven model quality (supersedes ADR-011 tier system)

**Status**: Accepted
**Date**: 2026-04-12
**Deciders**: Human + autonomous builder (Session 37)
**Supersedes**: ADR-011 (capability tier system)

## Context

ADR-011 introduced a four-level capability tier system (`NONE`, `BASIC`, `STANDARD`, `ADVANCED`) to classify models. The tier boundaries were empirical (based on measured quality, not parameter count), which was a good principle. However, the system conflated three independent concerns:

1. **Prompt strategy** — whether to use a binary prompt or a structured-reasoning prompt. Hard-coded as `use_enhanced = model_cap in (STANDARD, ADVANCED)`.
2. **Quality warnings** — telling users "your model may produce noisy results for this detector." Derived from the tier label, not from actual measurements.
3. **Model taxonomy** — five fixed model classes (`4B Local`, `9B Local`, `Cloud Nano`, `Cloud Small`, `Cloud Frontier`) that couldn't accommodate the diversity of models users actually run.

### Problems this caused

- **Users with untested models had no guidance.** A user with a 14B/16B/30B/70B local model, or a less common cloud API, had no place in the taxonomy. The only answer was "we don't know — benchmark it."
- **The tier label pretended to know things it didn't.** A 14B model might score between basic and standard, but the system forced it into one bucket or the other.
- **Prompt strategy was coupled to a config label**, not to measured quality. A user could set `model_capability = "standard"` for any model, gaining enhanced prompts regardless of whether the model actually handles them well.
- **The model classes list was a maintenance burden.** Every new model family required manually adding a new class or awkwardly fitting it into an existing one.

### What users actually need

| User situation | Need |
|----------------|------|
| 8 GB VRAM, privacy-required | "What works locally? What's noisy?" |
| 16–24 GB VRAM | "I have a bigger GPU — does Sentinel use it well?" |
| Cloud API available | "Cost vs quality tradeoffs" |
| Any model | "Will THIS model work well with THIS detector?" |

The answer to all of these is empirical benchmark data, not a taxonomy.

## Decision

### Replace the tier taxonomy with benchmark-driven quality ratings

The system shifts from "classify your model into a tier" to "benchmark your model, see what works."

#### Three independent concerns, cleanly separated:

**1. Prompt strategy (code-internal, not user-facing)**

Detectors support two prompt modes: `binary` (simple yes/no) and `enhanced` (structured reasoning). The system selects the mode based on:

1. **Benchmark data** (preferred): If `sentinel benchmark` has been run for this model+detector, and the quality rating is GOOD or better, use `enhanced`. Otherwise use `binary`.
2. **User override**: `model_capability` config still works as an explicit hint. Setting `model_capability = "standard"` forces `enhanced` prompts regardless of benchmark data.
3. **Default**: `binary` — safe for any model, robust even on weak ones.

**2. Quality ratings (empirical, per-model×detector)**

The compatibility matrix becomes `{model_name → {detector_name → QualityRating}}`:

- **Reference benchmarks**: Shipped with the code — our tested models (qwen3.5:4b, qwen3.5:9b, gpt-5.4-nano). These are the "known good" baseline.
- **User benchmarks**: Results from `sentinel benchmark` runs, stored in SQLite. Accumulated over time.
- **Untested**: Everything else. Displays "Untested — run `sentinel benchmark`" instead of guessing.

**3. Recommendations (editorial, not computed)**

A "Getting Started" section with practical advice for common situations (VRAM tiers, cloud budgets). This is human-written guidance, not a computed taxonomy.

#### Backward compatibility

- `CapabilityTier` enum remains in the codebase as a config mechanism.
- `model_capability = "basic"` / `"standard"` / `"advanced"` still works in `sentinel.toml`.
- The runner still warns when a detector's declared tier exceeds the configured capability.
- **New behavior**: When benchmark data exists for the current model+detector, it takes precedence over the tier label for prompt strategy selection.

#### Benchmark drill-down for power users

The existing `llm_log` table already records full prompt, response, model, timing, and verdict for every LLM call. Benchmark runs should expose this data so users can inspect exactly what prompt was sent, what context was included, and what the model output — enabling informed model selection decisions.

## Consequences

**Positive**:
- Honest about what we know and don't know — no pretending untested models fit a tier.
- Scales to any number of models without taxonomy maintenance.
- Prompt strategy is data-driven, not label-driven.
- Users with unusual hardware/models get a clear path: "benchmark it, see the results."
- Power users can drill into actual prompts and outputs to understand model behavior.

**Negative**:
- Cold-start problem for new users who haven't benchmarked yet. Mitigated by reference benchmarks shipped with the code and editorial recommendations.
- Slight increase in complexity: two sources of truth (reference + user benchmarks) that must be merged.
- `model_capability` config becomes a hint rather than the primary mechanism. May confuse users upgrading from older versions.

**Neutral**:
- The `CapabilityTier` enum and config field persist for backward compatibility and as an explicit override. They just stop being the sole driver of prompt strategy.

## Alternatives considered

**A. Expand the tier taxonomy with more buckets (8GB, 16GB, 24GB VRAM tiers)**:
Rejected. Parameter count and VRAM don't reliably predict quality. Two 14B models can perform very differently. The taxonomy would always be incomplete and need constant updates.

**B. Drop tiers entirely, benchmark only**:
Partially adopted. We keep `CapabilityTier` as a backward-compatible config hint but make benchmark data the primary signal. Pure "benchmark everything" has a cold-start problem.

## References

- ADR-011: Capability tier system (superseded by this ADR)
- ADR-013: Per-detector model providers (complementary — enables routing different detectors to different models)
- `src/sentinel/store/llm_log.py`: Existing LLM call logging (prompt, response, verdict, timing)
- `docs/reference/compatibility-matrix.md`: User-facing compatibility documentation
- `docs/reference/model-benchmarks.md`: Empirical benchmark data
