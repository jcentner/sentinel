# Model Benchmarks

Empirical comparison of Ollama models for the Sentinel LLM judge.

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
| low | 80 | 82 | 72 |
| medium | 13 | 13 | 23 |
| high | 2 | 2 | 0 |
| **Total** | **95** | **97** | **95** |

The 9B model promoted more findings from low to medium severity but eliminated both high-severity findings. This suggests it may be miscalibrating — flagging complexity findings (which have high detector confidence) as false positives.

## Recommendations

1. **Use qwen3.5:4b as default** — it fits entirely in 8 GB VRAM, runs at 53 tokens/s, and produces reasonable judgments. The 3× speed advantage over 9B is substantial for overnight batch runs.

2. **The 9B model's higher FP rejection rate needs investigation** for correctness. It may be rejecting legitimate findings that the 4B correctly confirms. A formal eval against ground truth with both models would clarify this.

3. **`num_ctx: 2048` is adequate** — our prompts use <50% of context. No need to increase.

4. **`num_predict: 512` is generous** — responses average ~110 tokens. Could reduce to 256 without truncation risk, saving ~10% generation time.

## Future Work

- Benchmark with `num_predict: 256` to measure speedup
- Run both models against the ground-truth fixture (`sentinel eval`) with LLM judge enabled to get formal precision/recall comparison
- Test Q6_K quantization for the 4B model (if more VRAM headroom is desired)
- Benchmark context gathering with embeddings enabled (adds ~500 tokens/finding from semantic context)
