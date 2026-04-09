# Benchmarking Guide

How to measure and compare Sentinel's detector and model performance.

## Quick Start

```bash
# Run all detectors against a repo (deterministic only)
sentinel benchmark <repo-path> --skip-judge

# Run with LLM-assisted detectors
sentinel benchmark <repo-path> --model qwen3.5:4b --provider ollama

# Filter to specific detectors
sentinel benchmark <repo-path> --detectors todo-scanner,lint-runner,dead-code

# Compare two runs
sentinel benchmark <any-repo> --compare benchmarks/run1.toml --compare benchmarks/run2.toml
```

## What Gets Measured

For each detector:
- **Finding count**: How many issues it finds
- **Duration (ms)**: Wall-clock time for that detector
- **Categories**: What kind of findings it produces
- **Tier**: deterministic, heuristic, or llm-assisted

For the full run:
- **Total findings**: Sum across all detectors
- **Total duration**: Wall-clock time for the entire benchmark
- **Eval metrics**: Precision, recall, and true/false positive counts (when ground truth is available)

## Ground Truth Evaluation

If the target repo contains a `ground-truth.toml` file, the benchmark automatically evaluates against it.

The format is documented in [tests/fixtures/SAMPLE-REPO-GROUND-TRUTH.md](../../tests/fixtures/SAMPLE-REPO-GROUND-TRUTH.md). Key sections:

```toml
exclude_detectors = ["dep-audit", "git-hotspots"]

[[expected]]
detector = "todo-scanner"
file_path = "main.py"
title = "TODO"

[[false_positives]]
detector = "todo-scanner"
file_path = "main.py"
title = "inside a string"
```

## Comparing Models

To compare how different models perform:

```bash
# Run with model A
sentinel benchmark ~/my-repo --model qwen3.5:4b --provider ollama

# Run with model B (change the model)
sentinel benchmark ~/my-repo --model llama3.2:3b --provider ollama

# Compare
sentinel benchmark ~/my-repo --compare benchmarks/*qwen*.toml --compare benchmarks/*llama*.toml
```

The comparison table shows per-detector finding counts and timing side by side.

## Output Format

Results are saved as TOML files in `benchmarks/` (configurable with `--output-dir`):

```toml
[benchmark]
repo_path = "/path/to/repo"
model = "qwen3.5:4b"
provider = "ollama"
total_findings = 32
total_duration_ms = 5503.0

[benchmark.eval]
precision = 1.0
recall = 1.0

[[benchmark.detectors]]
name = "todo-scanner"
finding_count = 8
duration_ms = 42.0
tier = "deterministic"
categories = ["todo-fixme"]
```

Use `--json-output` for machine-readable JSON instead of the human-friendly CLI output.

## Interpreting Results

- **High finding count ≠ good**: More findings may mean more noise. Precision matters more than volume.
- **Timing varies**: First runs are slower due to filesystem caching. Run 2-3 times for stable numbers.
- **Deterministic vs LLM**: `--skip-judge` runs only deterministic/heuristic detectors. Without it, LLM-assisted detectors (semantic-drift, test-coherence, docs-drift) also use the model.
- **dep-audit is slow**: It runs `pip-audit` which queries PyPI. Consider `--skip-detectors dep-audit` for faster iteration.
