# Benchmarks

Benchmark results from `sentinel benchmark` runs, tracking detector performance across different models and repositories.

## Benchmark Integrity Requirements

All benchmark results and quality ratings **must be empirical** — derived from actual `sentinel benchmark` runs against annotated ground truth. The following rules are non-negotiable:

1. **Never estimate ratings.** If a model×detector combination has not been benchmarked, it is "❓ Untested". Do not extrapolate from other models, parameter counts, or assumptions about model families.
2. **Never fudge numbers.** Every precision/recall/FP rate in the compatibility matrix must trace back to a specific benchmark run with a ground truth file. If the number can't be reproduced by running `sentinel benchmark`, it doesn't belong.
3. **Statistical significance matters.** A single TP or FP does not establish a rate. When N < 5 for a category, report the raw counts (e.g., "3 TP, 2 FP, N=5") rather than percentages. Ratings derived from fewer than 5 findings should be flagged as "preliminary".
4. **Synthesized data is not evidence.** Ground truth must come from real repositories where findings have been manually verified. Seeded fixtures (like sample-repo) are acceptable for regression testing but insufficient alone for quality claims — validate against real projects too.
5. **Separate deterministic from LLM-assisted.** Headline precision numbers dilute model impact because deterministic detectors are model-invariant. Always report per-category (deterministic vs LLM-assisted) metrics.
6. **Document provenance.** Each benchmark TOML file records the timestamp, model, provider, repo, and ground truth path. These are the audit trail.

## File Format

Each file is TOML with the naming convention: `<timestamp>-<repo>-<model>.toml`

## Usage

```bash
# Run a benchmark
sentinel benchmark <repo-path> --skip-judge

# Compare results
sentinel benchmark <repo-path> --compare benchmarks/file1.toml --compare benchmarks/file2.toml
```

## Baseline Results

All previous benchmark results purged on 2026-04-14 (pre-expanded sample-repo, stale detector versions). Fresh benchmarks will be generated per the [benchmarking plan](../docs/analysis/benchmarking-plan.md).
