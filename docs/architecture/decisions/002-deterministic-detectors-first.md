# ADR-002: Deterministic detectors as primary signal source

**Status**: Accepted
**Date**: 2026-03-28
**Deciders**: Project founder

## Context

A 4B local model (e.g., Qwen3.5 4B) is not reliable enough for open-ended code review. Letting it freely wander a repo and invent review comments produces mostly plausible-sounding noise. The system needs a different strategy for generating candidate findings.

## Decision

The primary signal sources are deterministic (Tier 1) and heuristic (Tier 2) detectors — linters, test runners, grep patterns, dependency audits, git-history analysis, docs-drift extraction. The LLM acts as a **judgment and summarization layer** over findings produced by these detectors, not as the primary signal source.

The detector tiers are:
1. **Deterministic**: Lint, test, TODO/FIXME, dep audit, SQLFluff, Semgrep. Cheap, reliable.
2. **Heuristic**: Git hotspots, churn, complexity, dead-code reachability. Model-free.
3. **LLM-assisted**: Model reads code + context and judges. Useful but false-positive-prone.

MVP should be mostly Tier 1 + 2, with Tier 3 reserved for judgment/summarization tasks.

## Consequences

**Positive**:
- False positive rate is controlled by the quality of deterministic detectors
- The LLM evaluates evidence rather than inventing conclusions
- Findings can cite specific tool output (lint rule, test failure) as evidence
- System works (in degraded mode) even without the LLM

**Negative**:
- Limited to what detectors can find — misses novel or unexpected issues
- More upfront work to integrate each detector tool
- LLM-only insights (e.g., "this API design feels off") are explicitly deprioritized

## Alternatives considered

- **LLM-primary review**: Let the model scan code directly and produce findings. Rejected because 4B models produce too much noise on open-ended review tasks.
- **Only deterministic tools, no LLM**: Would work but misses the value-add of synthesizing and explaining findings in context. The LLM adds real value as a judge, not as a discoverer.
