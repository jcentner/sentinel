# Benchmarking Plan

How to build statistically meaningful benchmark data for all Sentinel detectors.

**Governing decision**: ADR-018 (Benchmark Rigor as Core Engineering Discipline)

## Current State

### Ground truth coverage by detector category

| Detector | sample-repo | sentinel self-scan | pip-tools | Status |
|----------|-------------|-------------------|-----------|--------|
| complexity | 2 TP | 111 TP (assumed) | 20 TP (assumed) | Adequate |
| dead-code | 6 TP | 1 TP, 39 FP | 6 FP | Adequate (FP-rich) |
| docs-drift | 5 TP | 29 TP, 11 FP | 3 FP | Adequate |
| todo-scanner | 8 TP | 16 FP | 15 TP (assumed) | Adequate |
| lint-runner | 2 TP | 5 TP | 0 | Adequate |
| unused-deps | 5 TP | 2 FP | 3 FP | Adequate |
| stale-env | 5 TP | 0 | 0 | Fixture-only |
| git-hotspots | 0 | 9 TP | 3 TP | Adequate |
| cicd-drift | 0 | 3 FP | 0 | Minimal |
| **semantic-drift** | **1 TP** (→ **10 TP**) | **0** | **0** | **Needs annotation** |
| **test-coherence** | **2 TP** (→ **16 TP**) | **0** | **0** | **Needs annotation** |
| **inline-comment-drift** | **1 TP** (→ **16 TP**) | **0** | **0** | **Needs annotation** |
| **intent-comparison** | **0** (→ **8 TP**) | **3 TP, 3 FP** | **1 TP, 1 FP** | **Sparse** |

### Key gaps

1. **Three LLM detectors have zero ground truth on real repos.** The sample-repo has been expanded with seeded issues (10+ per detector), but real-repo annotations don't exist yet.
2. **Intent-comparison has N<5 on all model×repo combinations.** Even frontier gpt-5.4 has only 7 findings on real repos.
3. **No ground truth for enhanced-mode prompts.** All standard-tier entries are UNTESTED.

## Phase 1: Sample-repo baseline (can run immediately)

The expanded sample-repo now has seeded issues for all 4 LLM detectors:

| Detector | Expected TPs | True negatives |
|----------|-------------|----------------|
| semantic-drift | 10 | ~5 correct doc sections |
| test-coherence | 16 | ~8 correct tests |
| inline-comment-drift | 16 | ~8 correct docstrings |
| intent-comparison | 8 | ~6 consistent multi-artifact symbols |

### Commands to run

```bash
# Per-model benchmark against ground truth
sentinel benchmark tests/fixtures/sample-repo \
  --ground-truth tests/fixtures/sample-repo/ground-truth.toml \
  --model qwen3.5:4b --provider ollama --save

sentinel benchmark tests/fixtures/sample-repo \
  --ground-truth tests/fixtures/sample-repo/ground-truth.toml \
  --model qwen3.5:9b-q4_K_M --provider ollama --save

sentinel benchmark tests/fixtures/sample-repo \
  --ground-truth tests/fixtures/sample-repo/ground-truth.toml \
  --model gpt-5.4-nano --provider azure --save

sentinel benchmark tests/fixtures/sample-repo \
  --ground-truth tests/fixtures/sample-repo/ground-truth.toml \
  --model gpt-5.4-mini --provider azure --save

sentinel benchmark tests/fixtures/sample-repo \
  --ground-truth tests/fixtures/sample-repo/ground-truth.toml \
  --model gpt-5.4 --provider azure --save
```

### Expected outputs

Each run produces a TOML file with per-detector precision/recall and deterministic/LLM splits. The ground truth is well-seeded so we expect:

- **Good models** (cloud-small+): should find most seeded TPs and few FPs → precision >70%, recall >60%
- **Basic models** (4B/9B): should find some TPs but with higher FP rate → precision 30-60%
- **Nano**: intermediate — good on binary detectors, noisy on ICD

### What to do with results

1. Verify each model's findings against ground truth annotations
2. Any unexpected FPs: annotate them in `ground-truth.toml` under `[[false_positives]]`
3. Any missed TPs: check if the seeded issue is realistic enough, adjust if needed
4. Update `COMPATIBILITY_MATRIX` entries with real counts (tp=N, n=M, repos="sample-repo")

## Phase 2: Real-repo LLM detector annotation

This requires running LLM detectors on sentinel and pip-tools, then manually annotating each finding.

### Step 1: Run LLM scans on real repos

```bash
# Sentinel self-scan with each LLM detector individually
sentinel scan . --only semantic-drift --model gpt-5.4-mini --skip-judge --json-output > /tmp/sentinel-sd-mini.json
sentinel scan . --only test-coherence --model gpt-5.4-mini --skip-judge --json-output > /tmp/sentinel-tc-mini.json
sentinel scan . --only inline-comment-drift --model gpt-5.4-mini --skip-judge --json-output > /tmp/sentinel-icd-mini.json

# pip-tools
sentinel scan ~/pip-tools --only semantic-drift --model gpt-5.4-mini --skip-judge --json-output > /tmp/pip-sd-mini.json
sentinel scan ~/pip-tools --only test-coherence --model gpt-5.4-mini --skip-judge --json-output > /tmp/pip-tc-mini.json
sentinel scan ~/pip-tools --only inline-comment-drift --model gpt-5.4-mini --skip-judge --json-output > /tmp/pip-icd-mini.json
```

### Step 2: Annotate each finding

For each finding in the JSON output:
1. Read the source file at the indicated path/line
2. Compare the finding's claim against reality
3. Classify as TP (real issue) or FP (false alarm)
4. Record the FP pattern if applicable
5. Add to the ground truth TOML file

### Step 3: Run full benchmarks

Once ground truth is annotated:

```bash
sentinel benchmark . \
  --ground-truth benchmarks/ground-truth/local-repo-sentinel.toml \
  --model gpt-5.4-mini --save

sentinel benchmark ~/pip-tools \
  --ground-truth benchmarks/ground-truth/pip-tools.toml \
  --model gpt-5.4-mini --save
```

Repeat for each model class (4B, 9B, nano, mini, frontier).

### Expected effort

- Sentinel self-scan: ~20-50 LLM findings per detector per model (150-300 total annotations)
- pip-tools: ~10-30 LLM findings per detector per model (similar scale)
- Annotation time: ~2-3 minutes per finding for a human familiar with the codebase
- Total: 4-8 hours of annotation work across both repos

## Phase 3: Update compatibility matrix

After Phase 1 and Phase 2, update the matrix:

1. Replace all "UNTESTED" entries for LLM detectors with measured data
2. Add `tp=N, n=M, repos="..."` to every entry
3. Mark entries with N<5 as "Preliminary" in the notes
4. Downgrade entries where N is too small for the claimed rating

### Minimum sample requirements (ADR-018)

| Condition | Action |
|-----------|--------|
| N < 5 | Raw counts only, rating = "Preliminary" |
| N ≥ 5 | Can show percentage, still show counts |
| N ≥ 10, ≥2 repos | Rating is "Established" |
| Fixture-only data | Rating is "Fixture-only" |

## Phase 4: Ongoing maintenance

### When ground truth needs updating

- After changing a detector's prompt or filter logic
- After expanding the sample-repo with new seeded issues
- After significant code changes to a scanned real repo (sentinel or pip-tools)
- Quarterly re-validation: re-run benchmarks and spot-check annotations

### Adding new benchmark repos

When adding a new real-world repo to the benchmark suite:

1. Run a deterministic scan first (`--skip-llm --skip-judge`)
2. Annotate deterministic findings to establish baseline
3. Run LLM detectors one at a time, annotate each
4. Create the ground truth TOML file
5. Run full benchmark to verify precision/recall
6. Add the repo to the matrix's `repos_tested` field

### Candidate repos for expansion

Good benchmark repos should have:
- Active development with real drift (not just synthetic issues)
- Mix of well-documented and poorly-documented code
- Tests of varying quality (some stale, some current)
- Medium size (50-200 Python files) — large enough for signal, small enough to annotate

Candidates:
- **flask** or **FastAPI**: well-documented, actively maintained
- **black** or **ruff**: well-tested, minimal doc drift expected (good for FP testing)
- **poetry**: complex config/dependency management, likely docs-drift signal
