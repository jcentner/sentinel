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

## Detector Matrix

### Deterministic Detectors (no model needed for detection)

These detectors work identically regardless of model. The model is only used by the **judge** to filter findings after detection.

| Detector | Type | What It Does |
|----------|------|-------------|
| lint-runner | deterministic | Runs ruff lint on Python |
| eslint-runner | deterministic | Runs ESLint on JS/TS |
| todo-scanner | deterministic | Finds TODO/FIXME/HACK/XXX |
| docs-drift | deterministic | Broken links, stale paths, dep drift |
| unused-deps | deterministic | Declared deps not imported in source |
| stale-env | deterministic | .env docs vs actual env var usage |
| dep-audit | deterministic | Known vulnerabilities (pip-audit/npm) |
| go-linter | deterministic | go vet + staticcheck |
| rust-clippy | deterministic | cargo clippy |
| complexity | heuristic | High cyclomatic complexity / long functions |
| dead-code | heuristic | Exported symbols never imported elsewhere |
| git-hotspots | heuristic | High-churn, fix-heavy files |

**Model recommendation for deterministic detectors**: Any model works. The 4B local model is sufficient as judge for these. Skip the model entirely (`--skip-judge`) for fastest results.

### LLM-Assisted Detectors (model quality matters)

These detectors **use the model directly** to analyze code. Model quality directly impacts finding accuracy.

| Detector | 4B Local | 9B Local | Cloud Nano | Cloud Frontier |
|----------|----------|----------|------------|----------------|
| **semantic-drift** | 🔵 Good (<15% FP) | 🔵 Good (<15% FP) | 🟢 Excellent (<10% FP) | ❓ Untested |
| **test-coherence** | 🔴 Poor (~40% FP) | 🟡 Fair (~30% FP) | 🔵 Good (~15% FP) | ❓ Untested |

### LLM Judge (evaluates all findings)

| Role | 4B Local | 9B Local | Cloud Nano | Cloud Frontier |
|------|----------|----------|------------|----------------|
| **Judge** | 🔵 Good (~15% FP) | 🟡 Fair (~10% FP*) | 🔵 Good (~10% FP) | ❓ Untested |

\* The 9B model's low FP rate is misleading — it rejects 58% of findings, many of which are true positives. It over-filters.

## Key Findings

### semantic-drift works well on all models

The binary "in sync / needs review" prompt is robust even for the smallest model. All three tested models find the same core signals with similar accuracy. Use whatever model you have.

### test-coherence requires a capable model

The 4B model cannot reliably distinguish between:
- A CLI test using `CliRunner.invoke()` (correct pattern) ← flags as stale
- A test mocking HTTP responses (correct isolation) ← flags as stale
- A simple serialization test (matches method complexity) ← flags as stale

**Recommendation**: Use `gpt-5.4-nano` or equivalent cloud model for test-coherence. If privacy requires local-only, either accept the noise or skip this detector with 4B.

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
```

### The 9B model is not recommended

On 8 GB VRAM hardware, the 9B model partially offloads to CPU, making it 2–3× slower than 4B with no quality improvement. It offers no advantage over 4B for any detector.

## Model Classes Reference

| Class | Example | VRAM | Speed | Cost | Best For |
|-------|---------|------|-------|------|----------|
| **4B Local** | qwen3.5:4b | ~3.4 GB | ~53 tok/s | Free | Default — deterministic detectors + judge + semantic-drift |
| **9B Local** | qwen3.5:9b-q4_K_M | ~6.6 GB | ~19 tok/s | Free | Not recommended on 8 GB VRAM |
| **Cloud Nano** | gpt-5.4-nano | n/a | ~100 tok/s | ~$0.002/scan | test-coherence, highest precision |
| **Cloud Frontier** | gpt-5.4 | n/a | varies | Higher | Not yet benchmarked — untested |

## Capability Tiers Explained

Detectors declare a **minimum capability tier** — the weakest model class that can run them at all.

| Tier | Min Model | Detectors Using It |
|------|-----------|-------------------|
| **none** | No model | All deterministic + heuristic detectors |
| **basic** | 4B+ | semantic-drift, test-coherence (binary mode) |
| **standard** | 9B+ / cloud | Enhanced semantic-drift, enhanced test-coherence (structured analysis) |
| **advanced** | Frontier | Deep semantic analysis (planned, not yet implemented) |

**Important**: "Can run" ≠ "runs well." A 4B model *can* run test-coherence (basic tier), but produces ~40% FPs. The compatibility matrix above shows what actually works in practice.

## How These Numbers Were Measured

All ratings come from running Sentinel against real repos:

- **Sample-repo fixture**: 30+ seeded findings, ground truth annotated
- **Sentinel self-scan**: ~4500 LOC Python project
- **tsgbuilder**: Production Python CLI tool
- **wyoclear**: Production Next.js web app

Each run records findings, FP rates, and timing. See [model-benchmarks.md](model-benchmarks.md) for raw benchmark data.

Ratings are updated as new benchmarks are run. To contribute: run `sentinel benchmark` on your repo with different models and share results.
