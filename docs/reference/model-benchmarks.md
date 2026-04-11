# Model Benchmarks

Empirical comparison of models for Sentinel's LLM judge and LLM-assisted detectors.

## Test Setup

- **Target repo**: Sentinel self-scan (Python project, ~3600 LOC across 37 modules)
- **Hardware**: Windows 11 + WSL 2 Ubuntu, GPU with 8 GB VRAM
- **Ollama version**: Current as of 2026-04-06
- **Detectors**: 5 active for this repo (complexity, docs-drift, git-hotspots, lint-runner, todo-scanner)
- **Context**: `num_ctx` hardcoded at 2048 in judge.py (Ollama Modelfile default is 2048; model metadata says 262k)
- **Date**: 2026-04-06

## Context Usage

The judge prompt format produces prompts of **291–832 tokens** (avg ~523). Responses are capped at `num_predict: 512` and typically use **55–191 tokens** (avg ~110–133). Total context per call: ~630–960 tokens, well within the 2048 default.

**No need to increase `num_ctx`** — our prompts use ≤50% of the default. The models support 262k context, but larger contexts waste VRAM on KV cache. If future detectors produce much larger evidence blocks, we may revisit.

## Results

### Throughput

| Model | Params | Quant | VRAM Fit | Scan Time | LLM Calls | Avg/Call | Tokens/s |
|-------|--------|-------|----------|-----------|-----------|----------|----------|
| (no judge) | — | — | — | 5.8s | 0 | — | — |
| qwen3.5:4b | 4.7B | Q4_K_M | Full GPU | 5m 8s | 99 | 2.1s | 53.0 |
| qwen3.5:9b | 9.7B | Q4_K_M | Partial (72% GPU) | 14m 22s | 97 | 7.2s | 18.5 |

The 9B model is **2.9× slower** because ~28% of layers offload to CPU (8.92 GB model, 6.43 GB in VRAM).

### Quality: Verdict Distribution

| Verdict | 4B | 9B |
|---------|----|----|
| confirmed | 63 (64%) | 39 (40%) |
| likely_false_positive | 34 (34%) | 56 (58%) |
| parse errors | 2 (2%) | 2 (2%) |

The 9B model is **significantly more skeptical** — it marks 58% of findings as likely false positives vs 34% for the 4B model. Both models identified the same 2 parse-error cases (likely docs-drift findings with ambiguous evidence).

### Quality: Severity Distribution (after judge)

| Severity | No Judge | 4B | 9B |
|----------|----------|----|----|
| low | 54 | 82 | 72 |
| medium | 37 | 13 | 23 |
| high | 4 | 2 | 0 |
| **Total** | **95** | **97** | **95** |

> Note: The 4B run shows 97 findings vs 95 for no-judge/9B because runs were sequential — minor repo changes (new files) between runs caused 2 additional docs-drift findings. This does not reflect model behavior.

Both models significantly redistribute severity compared to raw detector output: the no-judge run has 4 high + 37 medium, but after LLM judgment the 4B model produces 2 high + 13 medium (lowering most to low), and the 9B is even more aggressive (0 high + 23 medium). Both models act as severity filters, which aligns with the design intent — the LLM judge reduces noise by downgrading speculative findings.

## Recommendations

1. **Use qwen3.5:4b as default** — it fits entirely in 8 GB VRAM, runs at 53 tokens/s, and produces reasonable judgments. The 3× speed advantage over 9B is substantial for overnight batch runs.

2. **The 9B model's higher FP rejection rate needs investigation** for correctness. It may be rejecting legitimate findings that the 4B correctly confirms. A formal eval against ground truth with both models would clarify this.

3. **`num_ctx: 2048` is adequate** — our prompts use <50% of context. No need to increase.

4. **`num_predict: 512` is generous** — responses average ~110 tokens. Could reduce to 256 without truncation risk, saving ~10% generation time.

## Future Work

- Benchmark with `num_predict: 256` to measure speedup
- Test Q6_K quantization for the 4B model (if more VRAM headroom is desired)
- Benchmark context gathering with embeddings enabled (adds ~500 tokens/finding from semantic context)
- Expand LLM detector ground truth to strengthen precision/recall measurements
- Test gpt-5.4-nano as judge (not just detector) when API quota allows

---

## LLM-Assisted Detector Benchmarks (2026-04-11)

Comparison of `semantic-drift` and `test-coherence` detectors across three models.

### Test Setup

- **Sample repo**: `tests/fixtures/sample-repo/` — a seeded fixture with deliberate doc-code drift and stale tests
- **Self-scan**: Sentinel's own codebase (~4500 LOC across 40+ modules)
- **Models**: qwen3.5:4b (Ollama, local), qwen3.5:9b-q4_K_M (Ollama, local), gpt-5.4-nano (OpenAI)
- **Mode**: `--skip-judge` (raw detector output, no judge severity re-assessment)
- **Date**: 2026-04-11

### Sample Repo Results

The sample repo has seeded drift: README describes config incorrectly, test files have stale/misleading docstrings.

| Detector | qwen3.5:4b | qwen3.5:9b | gpt-5.4-nano |
|----------|-----------|-----------|-------------|
| **semantic-drift** | 1 finding (6.0s) | 1 finding (11.2s) | 1 finding (1.7s) |
| **test-coherence** | 2 findings (3.1s) | 1 finding (7.0s) | 1 finding (3.0s) |
| **Total** | **3** | **2** | **2** |

All three models found the same core signal:
- **semantic-drift**: "Configuration" section in README.md vs `src/myapp/config.py` (correct — README describes stale paths)
- **test-coherence**: `test_main_returns_data` flagged by all three — test asserts trivial properties that don't validate implementation intent

The 4B model additionally flagged `test_main_runs` — a borderline finding (test only checks `not None`). The 9B model was more conservative. gpt-5.4-nano matched the 9B's selectivity but at 2-3× the speed.

**None of the models detected** the deliberately seeded `test_old_handler` (references a removed function), `test_keyboard_interrupt_handling` (tests unimplemented behavior), or `test_process_validates_xml_format` (describes XML validation that doesn't exist). These are harder coherence gaps that require deeper semantic reasoning.

### Sentinel Self-Scan Results

Running LLM detectors on Sentinel's own codebase:

| Detector | qwen3.5:4b | gpt-5.4-nano |
|----------|-----------|-------------|
| **semantic-drift** | 15 findings (45s) | 15 findings (18s) |
| **test-coherence** | 14 findings (39s) | 6 findings (31s) |
| **Total** | **29** | **21** |

Key differences:
- **semantic-drift**: Both models found the same 15 findings, all in `CONTRIBUTING.md`. The "Codebase Reading Guide" and other sections reference code files whose implementations have evolved. These are mostly true positives — the CONTRIBUTING doc does have stale descriptions.
- **test-coherence**: The 4B model flagged 14 tests vs 6 for gpt-5.4-nano. The 4B model included many false positives (e.g., CLI tests that use Click's test runner, provider tests using mock). gpt-5.4-nano was significantly more precise, mostly flagging tests where the docstring/name implies validation that the test doesn't actually perform.

### Analysis

| Metric | qwen3.5:4b | qwen3.5:9b | gpt-5.4-nano |
|--------|-----------|-----------|-------------|
| Speed (sample repo) | 9.2s | 18.2s | 4.7s |
| Speed (self-scan) | 84s | not tested | 49s |
| Sensitivity | High (more findings) | Conservative | Selective |
| FP rate (estimated) | ~40% test-coherence | ~30% | ~15% test-coherence |
| Cost | Free (local) | Free (local) | ~$0.002/scan |

### Recommendations

1. **Use qwen3.5:4b as the default** — free, local, reasonable quality. The higher FP rate on test-coherence is acceptable for a morning triage tool where the human reviews findings anyway.

2. **gpt-5.4-nano is the best quality option** — significantly lower FP rate, faster than local models, negligible cost. Recommended when privacy allows sending code snippets to OpenAI.

3. **The 9B model offers no advantage** — slower than 4B, same or fewer findings, partial CPU offload hurts throughput. Not recommended unless running on hardware with >10GB VRAM.

4. **semantic-drift works well across all models** — the binary "in sync / needs review" signal is robust even for the smallest model. FP rate is low because the prompt is highly constrained.

5. **test-coherence needs prompt refinement** — the 4B model flags too many tests that are actually fine (CLI integration tests, mock-based tests). The prompt may need to better distinguish "test validates behavior differently than name suggests" from "test uses a framework pattern the model doesn't recognize."
