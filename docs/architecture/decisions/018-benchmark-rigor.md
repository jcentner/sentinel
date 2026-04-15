# ADR-018: Benchmark Rigor as Core Engineering Discipline

**Status**: Accepted  
**Date**: 2026-04-14  
**Supersedes**: Strengthens ADR-016 (benchmark-driven model quality)

## Context

Sentinel's detectors are the core product. Their value is entirely determined by signal quality — a detector that surfaces 3 real issues is better than one that surfaces 20 noisy ones. We've repeatedly found that:

1. **Estimated ratings erode trust.** Prior sessions introduced "estimated" FP rates that were later found inaccurate. Once corrected, they revealed fundamental quality problems (e.g., ICD ~98% FP on nano) that had been obscured.
2. **FP rate alone is misleading.** A model producing 0 findings has 0% FP and 100% precision — and zero utility. The 9B judge rejects 58% of findings (~10% FP) but that's an over-filtering problem, not quality. FP rate hides recall failure.
3. **Sample size matters.** Rating "GOOD <15% FP" from a single finding on a 3-file fixture is meaningless noise. Our own benchmark integrity rules require N≥5 for rates, but the UI doesn't enforce or display this.
4. **Ground truth gaps undermine the entire system.** Three of four LLM detectors (semantic-drift, test-coherence, inline-comment-drift) had zero ground truth entries in real-repo benchmark files. Their "empirical" ratings were informed guesses from manual inspection, not reproducible evaluations.

This decision codifies benchmarking rigor as a non-negotiable engineering practice, not just a documentation nicety.

## Decision

### Benchmarks are the primary detector refinement tool

Every detector quality claim must be reproducible via `sentinel benchmark` with annotated ground truth. Manual inspection informs ground truth annotation, but the rating comes from the automated eval pipeline.

### Metrics must include precision, recall, raw counts, and sample size

The compatibility matrix must show:
- **Precision** as raw counts: `43% (3/7)` not just `~57% FP`
- **Recall** when ground truth TPs exist for the detector
- **Sample size adequacy**: whether N meets the minimum threshold for statistical meaningfulness
- **Repos tested**: which repositories contributed to the rating

FP rate alone is no longer sufficient for a quality rating.

### Ground truth is a first-class engineering artifact

The benchmark fixture (`tests/fixtures/sample-repo/`) and ground truth files (`benchmarks/ground-truth/`) are as important as the detector code itself. Specifically:

- The sample-repo must contain enough seeded issues per LLM detector (minimum 8 per detector) plus true negatives for measuring false positive rates
- Real-repo ground truth (sentinel self-scan, pip-tools) must include annotations for LLM detector findings, not just deterministic detectors
- Ground truth files must be updated when detector behavior changes

### Minimum thresholds for publishable ratings

| Condition | Requirement |
|-----------|-------------|
| N < 5 for a detector×model | Report raw counts only. Rating = "Preliminary" |
| N ≥ 5 | May report percentage rates. Still show raw counts |
| N ≥ 10 across ≥2 repos | Rating is "Established" — suitable for matrix display |
| Only synthetic (fixture) data | Rating is "Fixture-only" — validate against real repos |
| No ground truth exists | Rating = "Untested". No exceptions |

### The compatibility matrix is derived, not authored

Quality ratings in `COMPATIBILITY_MATRIX` must trace to benchmark TOML files and ground truth annotations. The path is: manual finding review → ground truth annotation → `sentinel benchmark` run → eval metrics → matrix entry. Any claim that skips a step is invalid.

## Consequences

### Positive
- Detector quality claims are reproducible and auditable
- Users see honest data including sample size, preventing overconfidence in sparse benchmarks
- Recall visibility prevents the "model filters everything and looks precise" failure mode
- Ground truth investment pays forward — every new benchmark run automatically evaluates against it

### Negative
- Many current "empirical" ratings will be downgraded to Untested or Preliminary until proper ground truth exists
- Sample-repo expansion and ground truth annotation require ongoing maintenance
- More metrics in the UI increases visual complexity

### Neutral
- This strengthens ADR-016's benchmark-driven approach but raises the bar — ADR-016 said "benchmark data takes precedence over tier labels" but didn't require specific sample sizes or multi-metric display
