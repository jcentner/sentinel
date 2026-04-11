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
| **(judge)** | 🔵 Good (~15% FP) | 🟡 Fair (~10% FP\*) | 🔵 Good (~10% FP) | ❓ Untested | ❓ Untested |

\* The 9B model's low FP rate is misleading — it rejects 58% of findings, many of which are true positives. It over-filters.

### Deterministic Detectors (no model needed for detection)

These 12 detectors work identically regardless of model. The model is only used by the **judge** to filter findings after detection.

lint-runner · eslint-runner · todo-scanner · docs-drift · unused-deps · stale-env · dep-audit · go-linter · rust-clippy · complexity · dead-code · git-hotspots

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

## Capability Tiers

Detectors declare a **minimum capability tier** — the weakest model class that can run them at all. But "can run" ≠ "runs well." The matrix above shows what actually works in practice.

Tier-to-model mapping is **empirical, not assumed from parameter count**. Two models with similar parameter counts can land in different tiers based on measured quality.

| Tier | What It Enables | Models That Qualify | Detectors |
|------|----------------|-------------------|-----------|
| **none** | Deterministic analysis only | No model needed | All 12 deterministic + heuristic detectors |
| **basic** | Binary LLM signals | 4B+ local (qwen3.5:4b) | semantic-drift (binary), test-coherence (binary — but noisy at 4B) |
| **standard** | Reasoning + structured output | Cloud nano+ (gpt-5.4-nano) | Enhanced semantic-drift, test-coherence with acceptable quality |
| **advanced** | Deep multi-artifact analysis | Cloud small/frontier (gpt-5.4-mini, Haiku 4.5, gpt-5.4) | Planned — not yet implemented |

### Why 9B local maps to basic, not standard

Independent aggregate rankings place qwen3.5:9b at ~32, only 5 points above qwen3.5:4b at ~27. Both are in the same capability class for Sentinel's tasks. Meanwhile gpt-5.4-nano scores ~38-44 — a different league — and our benchmarks confirm this: test-coherence goes from POOR/FAIR at 4B/9B to GOOD at cloud-nano.

The tier boundary between basic and standard is the empirically observed quality jump for test-coherence, not a parameter count threshold.

### Why cloud-small ≠ cloud-nano

GPT-5.4-mini (~38-49 depending on reasoning effort) and Claude Haiku 4.5 (~31-37) are both "fast production models" but they are not identical. Haiku 4.5 has near-frontier coding ability at one-third the cost of Sonnet 4, while GPT-5.4-mini is stronger on aggregate rankings at higher reasoning settings. They belong in the same broad tier (advanced) but are not interchangeable.

## Model Classes Reference

| Class | Tier | Example Models | VRAM | Speed | Best For |
|-------|------|----------------|------|-------|----------|
| **4B Local** | basic | qwen3.5:4b | ~3.4 GB | ~53 tok/s | Default — deterministic detectors + judge + semantic-drift |
| **9B Local** | basic | qwen3.5:9b-q4_K_M | ~6.6 GB | ~19 tok/s | Not recommended on 8 GB VRAM — use 4B instead |
| **Cloud Nano** | standard | gpt-5.4-nano | n/a | ~100 tok/s | test-coherence, highest precision, low cost |
| **Cloud Small** | advanced | gpt-5.4-mini, Claude Haiku 4.5 | n/a | varies | Near-frontier analysis (not yet benchmarked) |
| **Cloud Frontier** | advanced | gpt-5.4, Claude Sonnet 4 | n/a | varies | Frontier models (not yet benchmarked) |

## How These Numbers Were Measured

All ratings come from running Sentinel against real repos:

- **Sample-repo fixture**: 30+ seeded findings, ground truth annotated
- **Sentinel self-scan**: ~4500 LOC Python project
- **tsgbuilder**: Production Python CLI tool
- **wyoclear**: Production Next.js web app

Each run records findings, FP rates, and timing. See [model-benchmarks.md](model-benchmarks.md) for raw benchmark data.

Ratings are updated as new benchmarks are run. To contribute: run `sentinel benchmark` on your repo with different models and share results.
