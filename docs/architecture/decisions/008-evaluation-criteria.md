# ADR-008: Evaluation Criteria Defined Before Implementation

**Status**: Accepted
**Date**: 2026-04-04
**Deciders**: Autonomous builder (resolves OQ-007)

## Context

OQ-007 asks: "What eval criteria should be defined before building?" The open question notes that without measurable criteria, we can't evaluate whether Sentinel is working. The current thinking in OQ-007 identifies precision@k, false positive rate, time-to-review, and findings-per-run that lead to actual issues.

The vision lock (VISION-LOCK.md) includes evaluation criteria derived from OQ-007 and the critical review. This ADR formalizes the decision.

## Decision

Define the following evaluation metrics, tracked from Phase 1 MVP onward:

| Metric | Definition | MVP Target | Measurement Method |
|--------|-----------|------------|-------------------|
| **Precision@k** | Of the top-k findings in a report, how many are real issues or worth reviewing? | ≥ 70% | Manual annotation of findings after each test run |
| **False positive rate** | Percentage of findings per run that are not real issues | < 30% | Manual annotation |
| **Review time** | Wall-clock time to scan the morning report | < 2 minutes | Timed self-test during development |
| **Findings → issues rate** | Percentage of approved findings that become legitimate issues | Track only (no target) | Track via state store lifecycle |
| **Detector coverage** | Number of finding categories with at least one working detector | ≥ 3 for MVP | Count of implemented detectors |
| **Repeatability** | Same repo state produces identical findings across runs | 100% for deterministic (Tier 1/2) detectors | Automated: run twice, diff output |

### Implementation approach

1. **Eval script**: Create `sentinel eval` CLI command that re-runs against a known repo state and compares output against annotated ground truth.
2. **Annotation format**: A YAML file per test repo listing expected findings and their status (real/false-positive/borderline).
3. **Repeatability test**: Part of the standard test suite — run detectors twice on same input, assert identical output.
4. **Review time**: Measured manually during development; report format designed for scannability.

### When to measure

- Repeatability: automated, every CI run
- Precision@k and FP rate: after each detector is implemented, against at least one test repo
- Review time: at Phase 1 completion, human self-test
- Findings → issues: tracked in production use, no Phase 1 target

## Consequences

**Positive**: Clear success criteria exist before writing code. Prevents scope creep and "it works because I say so."

**Negative**: Manual annotation is labor-intensive. Eval requires maintaining test repos or fixtures.

**Neutral**: Targets are aspirational — they may be adjusted based on experience, recorded as vision revisions.

## Alternatives considered

- **No formal metrics, just vibes**: Rejected — the project's credibility depends on honesty about quality, and OQ-007 explicitly calls this out.
- **Automated eval only**: Impractical for Phase 1 — precision requires human judgment on whether a finding is "real."
- **Higher targets (≥ 90% precision)**: Premature — need baseline data first. Can tighten targets in later phases.
