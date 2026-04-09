# Benchmarks

Benchmark results from `sentinel benchmark` runs, tracking detector performance across different models and repositories.

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

| Repo | Findings | Detectors Active | Duration | Date |
|------|----------|-----------------|----------|------|
| sample-repo (fixture) | 32 | 7/14 | ~5.5s | 2025-04-09 |
| tsgbuilder | 134 | 7/14 | ~14s | 2025-04-09 |

Both baselines were run with `--skip-judge` (deterministic detectors only, no LLM).
