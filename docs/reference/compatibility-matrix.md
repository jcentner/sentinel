# Model-Detector Compatibility Matrix

Which models work well for which detectors — and which combinations to avoid.

> **Last updated**: 2026-04-11 | **Based on**: Self-scan, tsgbuilder, wyoclear, sample-repo benchmarks

## How to Read This

Each cell shows a **quality rating** based on empirical benchmarks:

| Rating | FP Rate | Meaning |
|--------|---------|---------|
| 🟢 Excellent | <10% | Recommended — high signal, minimal noise |
| 🔵 Good | 10–25% | Reliable for daily triage |
| 🟡 Fair | 25–40% | Usable but noisy — review findings carefully |
| 🔴 Poor | >40% | Not recommended — consider a stronger model |
| ⚪ N/A | — | Detector doesn't use a model for detection |
| ❓ Untested | — | No benchmark data yet |

## LLM-Assisted Detector Matrix

These detectors **use the model directly** to analyze code. Model quality directly impacts finding accuracy.

| Detector | 4B Local | 9B Local | Cloud Nano | Cloud Small | Cloud Frontier |
|----------|----------|----------|------------|-------------|----------------|
| **semantic-drift** | 🔵 Good (<15% FP) | 🔵 Good (<15% FP) | 🟢 Excellent (<10% FP) | ❓ Untested | ❓ Untested |
| **test-coherence** | 🔴 Poor (~40% FP) | 🟡 Fair (~30% FP) | 🔵 Good (~15% FP) | ❓ Untested | ❓ Untested |
| **intent-comparison** | ❓ Untested | ❓ Untested | ❓ Untested | ❓ Untested | ❓ Untested |
| **(judge)** | 🔵 Good (~15% FP) | 🟡 Fair (~10% FP\*) | 🔵 Good (~10% FP) | ❓ Untested | ❓ Untested |

\* The 9B model's low FP rate is misleading — it rejects 58% of findings, many of which are true positives. It over-filters.

### Deterministic Detectors (no model needed for detection)

These 14 deterministic detectors work identically regardless of model. The model is only used by the **judge** to filter findings after detection.

lint-runner · eslint-runner · todo-scanner · docs-drift · unused-deps · stale-env · cicd-drift · architecture-drift · dep-audit · go-linter · rust-clippy · complexity · dead-code · git-hotspots

**Model recommendation for deterministic detectors**: Any model works. The 4B local model is sufficient as judge for these. Skip the model entirely (`--skip-judge`) for fastest results.

## Key Findings

### semantic-drift works well on all models

The binary "in sync / needs review" prompt is robust even for the smallest model. All three tested models find the same core signals with similar accuracy. Use whatever model you have.

### test-coherence requires cloud-nano or better

The 4B model cannot reliably distinguish between:
- A CLI test using `CliRunner.invoke()` (correct pattern) ← flags as stale
- A test mocking HTTP responses (correct isolation) ← flags as stale
- A simple serialization test (matches method complexity) ← flags as stale

**Recommendation**: Use `gpt-5.4-nano` or equivalent for test-coherence. If privacy requires local-only, either accept the noise or skip this detector with 4B.

### inline-comment-drift (new — no benchmark data yet)

Uses the same binary prompt pattern as semantic-drift. Expected to work well at 4B for clear factual inaccuracies (wrong parameter names, wrong return values). May need cloud-nano for subtle semantic drift in complex docstrings. Python-only in v1.

### intent-comparison (new — ADVANCED tier, no benchmark data yet)

Multi-artifact triangulation: gathers code, docstring, tests, and doc sections for each function, then asks the LLM for contradictions between any pair. Requires `CapabilityTier.ADVANCED` — use frontier-class models (GPT-5.4-nano or better). Multi-artifact prompts are significantly larger than pairwise, and reliable cross-reference reasoning needs stronger models. Python-only in v1.

Configure per-detector model in `sentinel.toml`:

```toml
[sentinel]
provider = "ollama"
model = "qwen3.5:4b"

# Route test-coherence to a more capable model
[sentinel.detector_providers.test-coherence]
provider = "openai"
model = "gpt-5.4-nano"
api_base = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model_capability = "standard"
```

### The 9B model is not recommended on 8 GB VRAM

On 8 GB VRAM hardware, the 9B model partially offloads to CPU, making it 2–3× slower than 4B with only marginal quality improvement. The aggregate quality gap between 4B and 9B (scores ~27 vs ~32) does not justify the speed penalty for Sentinel's use cases.

## Capability Tiers (backward-compatible config hint)

The `model_capability` config field is preserved for backward compatibility. It provides an explicit override for prompt strategy selection. **When benchmark data exists for your model, it takes precedence.** See [ADR-016](../architecture/decisions/016-benchmark-driven-model-quality.md).

| Config value | Prompt mode | When to use |
|-------------|-------------|-------------|
| `"basic"` (default) | Binary prompts | Safe default. Works with any model. |
| `"standard"` | Enhanced prompts | When you *know* your model handles structured reasoning well. |
| `"advanced"` | Enhanced prompts | Same as standard (future detectors may differentiate). |

## Recommendations by Situation

These are editorial recommendations, not computed from a taxonomy. Your mileage may vary — run `sentinel benchmark` for your specific setup.

| Your Situation | Recommended Setup |
|----------------|-------------------|
| **8 GB VRAM, privacy-required** | qwen3.5:4b — works well for everything except test-coherence. Skip test-coherence or accept noise. |
| **12–16 GB VRAM, privacy-required** | Larger local model (14B class). Run `sentinel benchmark` to verify quality — likely better than 4B/9B. |
| **24+ GB VRAM** | 30B–70B local model. Should perform well — benchmark to confirm and unlock enhanced prompts. |
| **Cloud OK, budget-sensitive** | gpt-5.4-nano for LLM detectors, local 4B for deterministic. Best cost/quality ratio tested. |
| **Cloud OK, quality-first** | gpt-5.4-mini or Claude Haiku 4.5 for all LLM detectors. |
| **CPU-only (no GPU)** | qwen3.5:4b on CPU — slow but functional. Consider cloud API for LLM detectors. |

## Benchmarked Models

Our reference benchmarks cover these models. For all other models, run `sentinel benchmark --model <name>` to generate your own quality data.

| Model | Type | VRAM / Cost | Speed | Notes |
|-------|------|-------------|-------|-------|
| **qwen3.5:4b** | Local | ~3.4 GB | ~53 tok/s | Best value for 8 GB VRAM. Default recommendation. |
| **qwen3.5:9b-q4_K_M** | Local | ~6.6 GB | ~19 tok/s | Marginal improvement over 4B at 2–3× slower. Not recommended on 8 GB. |
| **gpt-5.4-nano** | Cloud | Low cost | ~100 tok/s | Substantially stronger. Best tested model for test-coherence. |

Models like gpt-5.4-mini, Claude Haiku 4.5, larger local models (14B, 30B, 70B), and other providers are not yet benchmarked. Quality is unknown until measured — the system defaults to conservative (binary) prompts for untested models.

## How These Numbers Were Measured

All ratings come from running Sentinel against real repos:

- **Sample-repo fixture**: 30+ seeded findings, ground truth annotated
- **Sentinel self-scan**: ~4500 LOC Python project
- **tsgbuilder**: Production Python CLI tool
- **wyoclear**: Production Next.js web app

Each run records findings, FP rates, and timing. See [model-benchmarks.md](model-benchmarks.md) for raw benchmark data.

Ratings are updated as new benchmarks are run. To contribute: run `sentinel benchmark` on your repo with different models and share results.
