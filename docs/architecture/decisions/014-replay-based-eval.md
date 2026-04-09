# ADR-014: Replay-Based Eval for Judge and Synthesis Paths

**Status**: Accepted
**Date**: 2026-04-10
**Supersedes**: —
**Deciders**: Autonomous builder agent (Session 25)
**Related**: ADR-008 (eval criteria), OQ-013

## Context

The eval system (`sentinel eval` and CI gate) runs with `skip_judge=True`, measuring only raw detector output against ground truth. The judge, synthesis, and full pipeline — the most business-critical paths — have zero eval coverage. When prompts change or parsing logic is refactored, regressions in the judge path are invisible until a real scan is run.

OQ-013 identified this gap and proposed several approaches. The replay approach was identified as highest ROI.

## Decision

Add a **replay-based full-pipeline eval mode** that exercises the judge and synthesis paths deterministically without requiring a live model.

### Components

1. **ReplayProvider**: A `ModelProvider` implementation that returns pre-recorded LLM responses matched by SHA-256 prompt hash. On hash miss, returns a safe default that confirms the finding.

2. **RecordingProvider**: A `ModelProvider` wrapper that delegates to a real provider while recording all prompt→response pairs to JSON for later replay.

3. **`sentinel eval --full-pipeline`**: Runs the scan with `skip_judge=False`, exercising the judge on all findings. Requires either `--replay-file` (for CI/offline) or a configured live provider.

4. **Per-detector breakdown**: `EvalResult` now includes per-detector precision/recall and optional judge-specific metrics (confirmation rate, rejection rate, wrongly-rejected TPs).

### Workflow

- **Recording**: `sentinel eval <repo> --full-pipeline --record-responses judge-recordings.json` — uses a live model, saves responses for later replay.
- **Replay** (CI): `sentinel eval <repo> --full-pipeline --replay-file judge-recordings.json` — deterministic, no model needed.
- **Prompt regression detection**: If prompt templates change, hashes no longer match, replay falls back to defaults, and the test signals that recordings need updating.

## Consequences

- **Positive**: The judge path now has deterministic CI coverage. Prompt template regressions are detectable. Per-detector breakdown pinpoints precision/recall changes to specific detectors.
- **Negative**: Replay files must be re-recorded when prompts change or ground truth evolves. Hash-based matching is rigid by design (this is a feature, not a bug).
- **Trade-off**: The replay default confirms all findings — this is conservative (won't cause false failures) but means hash misses test integration without testing judgment quality.

## Alternatives Considered

1. **Live model in CI**: Run the judge with a real model during CI. Rejected — non-deterministic, requires model access in CI, slow, and flaky.
2. **Hardcoded mock responses**: Use a single static judge response for all findings. Implemented as the default fallback, but insufficient alone because it doesn't test prompt regression.
3. **Snapshot testing**: Compare full prompt text against committed snapshots. Rejected — too brittle (any finding content change breaks snapshots), and doesn't test the JSON parsing/severity adjustment logic.
