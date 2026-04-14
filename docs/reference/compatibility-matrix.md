# Model-Detector Compatibility Matrix

Which models work well for which detectors — and which combinations to avoid.

> **Last updated**: 2026-04-14 | **Based on**: sample-repo, pip-tools, sentinel self-scan benchmarks

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
| **semantic-drift** | 🔵 Good (<15% FP) | 🔵 Good (<15% FP) | 🟢 Excellent (<10% FP) | 🔵 Good (<15% FP) | 🔵 Good (<15% FP) |
| **test-coherence** | 🔴 Poor (~40% FP) | 🟡 Fair (~30% FP) | 🔵 Good (~15% FP) | 🔵 Good (~15% FP) | 🔵 Good (~15% FP) |
| **inline-comment-drift** | ❓ Untested | ❓ Untested | 🟡 Fair (~40% FP) | 🟢 Excellent (<10% FP) | ❓ Untested |
| **intent-comparison** | 🔵 Good (est, N=1) | 🔵 Good (est, N=1) | 🟡 Fair (est) | 🔵 Good (est) | 🔵 Good (est) |
| **(judge)** | 🔵 Good (~15% FP) | 🟡 Fair (~10% FP\*) | 🔵 Good (~10% FP) | ❓ Untested | ❓ Untested |

\* The 9B model's low FP rate is misleading — it rejects 58% of findings, many of which are true positives. It over-filters.

**Judge caveat**: `sentinel benchmark` does NOT run the judge — it measures raw detector output only. Judge ratings for 4B, 9B, and cloud-nano come from `sentinel scan` verdict distributions. Cloud-small and cloud-frontier judge quality has not been measured.

### Deterministic Detectors (no model needed for detection)

These 13 deterministic detectors work identically regardless of model. The model is only used by the **judge** to filter findings after detection.

lint-runner · eslint-runner · todo-scanner · unused-deps · stale-env · cicd-drift · architecture-drift · dep-audit · go-linter · rust-clippy · complexity · dead-code · git-hotspots

**Note**: docs-drift is hybrid — its link/path/dep checks are deterministic, but it optionally uses the LLM for doc-code semantic comparison when a provider is available. It is classified as LLM-assisted in the codebase.

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

### inline-comment-drift — model quality matters here

Finds real docstring-code drift. With updated ground truth (3 seeded TPs in sample-repo):
- **nano**: 5 findings (3 TP, 2 FP = 60% precision) — most aggressive
- **mini**: 2 findings (2 TP, 0 FP = 100% precision) — most selective
- On pip-tools: nano 16, mini 8 findings (no LLM ground truth yet)

**Mini is recommended** for this detector — it finds the real issues without the noise. **Very slow**: ~303s on pip-tools due to serial per-function LLM calls.

### intent-comparison — v2 redesign validated across 5 models

ICD v2 (Phase 15) adds post-LLM filtering with 3 gates: structural validity, specificity/vagueness rejection, evidence quote verification. Benchmarked across 3 repos x 5 models.

**Finding counts (ICD v2):**

| Model | sample-repo | pip-tools | sentinel | v1 pip-tools |
|-------|------------|-----------|----------|-------------|
| qwen3.5:4b | 1 (1 TP) | 3 | 15 | — |
| qwen3.5:9b | 1 (1 TP) | 2 | 6 | — |
| gpt-5.4-nano | 3 (1 TP) | 17 | 47 | 20 |
| gpt-5.4-mini | 2 (1 TP) | 6 | 30 | 31 |
| gpt-5.4 | 3 (1 TP) | 1 | 15 | 35 |

**Important**: All ICD ratings are **estimates** inferred from finding counts on repos without ICD ground truth. Sample-repo has only N=1 ICD TP. Fewer findings may indicate better precision **or** lower recall — not yet distinguishable without annotated ground truth on pip-tools/sentinel.

Sample-repo precision (the only ground-truth data): nano=33%, mini=50%, gpt-5.4=33%, 4B=100%, 9B=100%. These are N=1 measurements — not statistically reliable.

The detector remains disabled by default (TD-057) pending expansion of ICD ground truth. Run with `--detectors intent-comparison` to include it explicitly.

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
| **gpt-5.4-mini** | Cloud | Low cost | ~100 tok/s | Strong for all LLM detectors. Best pip-tools data. |
| **gpt-5.4** | Cloud | Medium cost | ~100 tok/s | Limited data — ~12 API calls on tiny fixture repo. Not meaningfully differentiated from mini. |

Models like Claude Haiku 4.5, larger local models (14B, 30B, 70B), and other providers are not yet benchmarked. Quality is unknown until measured — the system defaults to conservative (binary) prompts for untested models.

## How These Numbers Were Measured

**Important**: `sentinel benchmark` measures **raw detector output** against ground truth — it does NOT run the judge or synthesis pipeline. Precision/recall numbers reflect detector quality, not end-to-end scan quality. Judge quality ratings (4B, 9B, nano) were measured separately from `sentinel scan` verdict distributions.

Headline precision (e.g., "92% precision") is diluted by deterministic/heuristic detectors, which produce identical results regardless of model. Model quality only affects the 5 LLM-assisted detectors (semantic-drift, test-coherence, inline-comment-drift, intent-comparison, and parts of docs-drift). On the 3-file sample-repo fixture, 27 of 36–40 findings (varies by model) come from deterministic/heuristic detectors. Use the per-category LLM precision to compare models.

Benchmark repos:

- **Sample-repo fixture**: 37 seeded findings including 3 ICD TPs, ground truth annotated (benchmarked on 2 cloud models with per-category eval). 3 source files — small but meaningful for LLM detector comparison.
- **pip-tools**: Real-world Python project, 38 annotated findings (deterministic only — LLM detector ground truth needed). Benchmarked on 2 cloud models.
- **Sentinel self-scan**: Python project, 226 deterministic findings, 61 annotated

Each run records findings, FP rates, and timing. See [model-benchmarks.md](model-benchmarks.md) for raw benchmark data.

Ratings are updated as new benchmarks are run. To contribute: run `sentinel benchmark` on your repo with different models and share results.
