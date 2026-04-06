# VISION-REVISION-001: Pipeline Order Optimization

> **Created**: 2026-04-04
> **Applies to**: VISION-LOCK.md §"MVP Scope (Phase 1)"

## Change

The locked vision specifies the pipeline order as:

> detect → gather context → judge → deduplicate → report

The implemented order is:

> detect → fingerprint → deduplicate → gather context → judge → store → report

## Rationale

1. **Efficiency**: Running context gathering and LLM judgment on all raw findings (including duplicates and suppressed items) wastes compute and Ollama inference time. Deduplicating first means the expensive steps only run on findings that will appear in the report.
2. **Correctness**: Fingerprinting must happen before deduplication (dedup requires fingerprints to compare against the state store). This was implicit in the original spec but not explicit.
3. **No information loss**: Deduplication only removes (a) suppressed findings and (b) within-run duplicates. Neither class benefits from LLM judgment — suppressed findings are user-dismissed, and duplicates are identical by definition.

## Impact

- The architecture overview diagram and VISION-LOCK pipeline description are no longer accurate.
- Context gathering and LLM judgment now operate on a smaller, higher-signal set of findings.
- No change to external behavior: the morning report, finding schema, and detector contract are unaffected.

## Decision

Accept the implemented order as the canonical pipeline. Update documentation to match.
