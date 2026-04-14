# LLM Detector Evaluation — Prompt, Context, and Quality Analysis

> **Date**: 2026-04-14 | **Purpose**: Comprehensive evaluation of all LLM-assisted detectors

## Executive Summary

Sentinel has 5 LLM-assisted detectors. Three work well (semantic-drift, test-coherence, inline-comment-drift). One is severely underperforming on non-frontier models (intent-comparison — 43% precision on frontier, <5% on everything else). One is untested at the LLM level (docs-drift). The dominant failure mode across detectors is **insufficient context for the task asked** and **prompt ambiguity that weaker models exploit**.

### Key Findings

1. **Binary prompts outperform enhanced prompts for weaker models.** This validates ADR-016's approach — but the system should go further. For nano-class models, even the binary prompt asks too much in multi-artifact scenarios. (Observed pattern across all benchmarked model×detector combinations — see [compatibility-matrix.md](../reference/compatibility-matrix.md) for per-model ratings.)
2. **Context truncation is the invisible FP driver.** When functions are truncated at 1500 chars, the model sees a partial implementation and flags "missing behavior" that actually exists past the truncation point.
3. **Intent-comparison is fundamentally over-scoped.** Asking a model to cross-reference 4 artifact types in a single prompt exceeds the reasoning capability of most models. The 98% FP rate on nano isn't a prompting problem — it's a task design problem.
4. **docs-drift's LLM path is unbenchmarked and has no prompt adaptation.** Users deploying with a model provider silently get LLM-assisted docs-drift with no quality data.
5. **The "binary = safe default" hypothesis is validated for 3 of 4 detectors.** For semantic-drift, test-coherence, and inline-comment-drift, the binary signal works well with Good+ models.

## Per-Detector Analysis

### 1. semantic-drift — Well-designed, works across models

**Quality**: 🟢 Works well across all tested models (4B through frontier).

**Why it works**:
- Task is simple: "does this doc section match this code?" — binary comparison of two artifacts
- Context limits (800 doc + 2000 code chars) are sufficient for most doc sections
- The prompt explicitly says "Ignore style differences, minor wording choices, and documentation that is simply less detailed" — this gives models clear permission to say "no issue"
- No multi-artifact complexity

**Concerns**:
- No per-file or per-scan cap. On a repo with 20 key docs each having 30 sections, this could make hundreds of LLM calls.
- No risk-based prioritization — sends all section/code pairs regardless of churn.
- Enhanced prompt adds a 6-point checklist but the quality improvement over binary is marginal because the task itself is simple.

**Recommendation**: No prompt changes needed. Consider adding per-scan caps (e.g., 50) to prevent cost runaway on large repos. Binary prompt is sufficient even for advanced models here — the task doesn't benefit from structured reasoning.

### 2. test-coherence — Good design, weak model tolerance is key

**Quality**: 🔴 4B | 🟡 9B | 🔵 Nano+ 

**Why weaker models struggle**:
- The prompt must understand test framework patterns (mocking, CliRunner, fixtures). A 4B model doesn't reliably distinguish "mock that replaces core logic" from "mock that replaces I/O boundary".
- The COHERENT patterns list in the prompt (CLI CliRunner, mocked I/O, simple methods, error handling) is a good mitigation but 4B models don't reliably apply exclusion lists.
- Context limits (1500+1500 binary) are tight. A test function + its impl can each easily exceed 1500 chars. When truncated, the model sees an incomplete implementation and flags "missing coverage" for behavior it literally can't see.

**Prompt quality**:
- The explicit "A test is COHERENT (do NOT flag)" section is excellent — this is what makes the binary prompt work for nano+.
- The negative examples (CliRunner, mock I/O, simple assertions, error handling) are grounded in real FP patterns from earlier sessions.
- Enhanced prompt adds "5-point evaluation" but models that can handle that level of analysis already get low FP rates on binary.

**Per-capability consideration**: For 4B/basic models, the binary prompt is already as good as it gets. The real question is whether to **skip test-coherence entirely** on basic models rather than produce ~40% FP output. The system currently warns but doesn't suppress.

**Recommendation**: 
- Consider a config option to auto-disable specific detectors when benchmark quality is POOR for the configured model. This is more honest than producing noisy output with a warning badge.
- Context truncation (1500 chars) is too aggressive for implementation functions. Many Python functions are 30-80 lines (1500-4000 chars). Consider increasing binary limit to 2500 chars — the model can handle it and the precision gain from seeing the full function outweighs the cost.

### 3. inline-comment-drift — Solid, slow, reasonable

**Quality**: 🟡 Nano | 🟢 Mini+

**Key design features**:
- Per-scan cap of 100 is well-chosen. Prevents cost explosion.
- Per-file cap of 20 is reasonable.
- Risk-based sorting ensures high-churn files are analyzed first within the budget.
- Minimum docstring length (30 chars) filters trivial cases.

**Why nano is Fair, not Good**:
- The binary prompt says "Flag it ONLY if the docstring makes factually wrong claims" — this is clear and specific. But nano still flags docstrings that are "incomplete but not wrong" about 40% of the time.
- The issue is nano's difficulty with the "being incomplete is not the same as being wrong" distinction. This is a model limitation, not a prompt problem.

**Slow execution**: ~303s on pip-tools because each function gets a separate LLM call, serially. This is the #1 UX issue for this detector. Could be mitigated by batching multiple functions per prompt (e.g., "analyze these 5 docstring/code pairs") but that risks context confusion in weaker models.

**Recommendation**: No prompt changes needed. The performance issue (serial per-function calls) is the priority improvement — consider async batching for this detector specifically.

### 4. intent-comparison — Fundamentally over-scoped

**Quality**: 🔴 All models (nano ~98% FP, mini ~96% FP, frontier ~57% FP)

**Root cause analysis**:

The intent-comparison detector asks the model to:
1. Read up to 4 different artifact types (code, docstring, tests, docs)
2. Cross-reference all pairs for factual contradictions
3. Quote evidence from both sides
4. Distinguish contradictions from "different wording for same concept"

This is the hardest LLM task in Sentinel. Even gpt-5.4 (frontier) only achieves 43% precision. The fundamental problem isn't the prompt — it's the task scope.

**Specific failure modes** (from Session 49 annotation):
1. **Hallucinated test assertions** (dominant): Model claims `test_get_dependencies` asserts `== []` when it doesn't. The model fabricates evidence to support a "contradiction" it wants to find.
2. **Partial class reading**: With context limits (1200 code chars), the model sees the first half of a class, misses methods, and flags docstring as wrong.
3. **Parameter name confusion**: Model confuses `num_ctx` with `max_tokens` and flags a "contradiction".
4. **Irrelevant doc citations**: Model treats benchmark tables, changelogs, and glossary entries as behavioral specifications.

**Why the binary prompt doesn't help enough**:
- The binary prompt for ICD already has explicit FP and TP examples. It has post-LLM filtering (4 gates). It requires quoting both sides. Despite all this, models still hallucinate evidence because the task complexity exceeds their capacity.
- The FP examples are good ("different wording ≠ contradiction", "missing coverage ≠ contradiction") but models don't generalize these examples to novel cases.

**Per-capability tier analysis**:
- **Basic (4B/nano)**: Task is impossible at this capability level. Even a perfectly crafted prompt won't enable a 4B model to reliably cross-reference 4 artifacts without fabricating connections.
- **Standard (mini)**: Still too noisy. Mini can follow the format correctly but still hallucinates evidence.
- **Advanced (frontier)**: 43% precision means more TPs than FPs per finding, barely. This is the only model tier where ICD produces actionable output, and even then the volume is low enough (7 findings) that manual review is feasible.

**Possible redesign directions**:
1. **Reduce scope**: Instead of 4-way triangulation, do pairwise comparison (code vs docstring, code vs test, code vs docs) — this is what the other 3 detectors already do successfully. ICD's theoretical advantage (catching inconsistencies that pairwise misses) is not realized because models can't handle the complexity.
2. **Two-pass verification**: First pass generates candidate contradictions. Second pass (separate LLM call) verifies each candidate by re-reading the relevant artifacts. This catches hallucinated evidence because the verification prompt can focus on one specific claim.
3. **Restrict to frontier models**: Keep ICD but make it truly gated — not just disabled by default, but refusing to run unless benchmark data shows GOOD+ quality for the configured model. Users with nano/mini would get a clear "ICD requires gpt-5.4 or better" message rather than noisy output.

**Recommendation**: ICD should remain disabled by default. The most promising improvement path is **two-pass verification** — it directly targets the dominant FP pattern (hallucinated evidence) without requiring a fundamental redesign. The current single-pass architecture cannot reliably self-verify.

### 5. docs-drift (LLM path) — Unbenchmarked, no adaptation

**Quality**: ❓ Untested across all models

**Current state**:
- LLM path activates on key docs (README, CONTRIBUTING, INSTALL, GETTING-STARTED) when a provider is available and `skip_llm` is not set
- Uses a single prompt (no binary/enhanced distinction) — no `should_use_enhanced_prompt()` call
- No `capability_tier` property declared — defaults to base class
- Not included in the LLM-assisted matrix until this evaluation
- No test coverage for the LLM path in benchmarks

**The gap**: A user who configures `provider = "ollama"` and `model = "qwen3.5:4b"` silently gets LLM-assisted doc-code comparison on their key docs. There is no warning, no quality rating, and no benchmark data to tell them whether the results are useful or noise.

**Prompt assessment**:
- The prompt is simple and clear: "compare doc code block against actual source code"
- Context limits (1000 doc + 2000 code chars) are reasonable
- The task is similar to semantic-drift (pairwise comparison) and should work at similar quality levels
- But without benchmarks, we're guessing

**Recommendation**:
1. Add docs-drift to ground truth annotations for at least sample-repo (seed a doc code block that is stale)
2. Add `should_use_enhanced_prompt()` support (binary/enhanced prompt adaptation)
3. Add a `capability_tier` property (BASIC — same as semantic-drift, since the task complexity is similar)
4. Run benchmarks across models to establish quality ratings
5. Until benchmarked, the compatibility matrix should show ❓ Untested (now done)

## Cross-Cutting Issues

### Context truncation as hidden FP driver

All detectors truncate context (600–3000 chars depending on mode). For LLM detectors analyzing code, a typical Python function is 20-60 lines. At ~50 chars/line, that's 1000-3000 chars. Functions at the upper end get truncated under binary limits.

When the model sees a truncated function, it may:
- Flag "missing error handling" that exists past the truncation
- Flag "missing return path" that comes after the visible code
- Claim the function "doesn't implement X" when X is in the second half

**This is not a prompt problem — it's a context budget problem.** The binary limits were set conservatively for small-context models (2K context window), but even 4B models now support 8K+ context. Consider:
- Increasing binary limits to match what the model's context window can handle
- Passing `num_ctx` from the model's actual context size rather than hardcoding 2048
- Adding a comment in the prompt: "Note: this function may be truncated. Only flag issues visible in the provided code."

### The "basic" tier question

The user asked: "Can we set 'basic' for a detector for gpt-5.4-nano and get better accuracy because we're using a binary signal?"

**Answer: mostly yes, and this is already the default behavior.** The system already uses binary prompts for models that don't have GOOD+ benchmark data (ADR-016). For nano specifically:
- semantic-drift: binary prompt, Good quality — ✅ working as intended
- test-coherence: binary prompt, Good quality — ✅ working as intended
- inline-comment-drift: binary prompt, Fair quality — the binary signal helps but nano still struggles with the "incomplete ≠ wrong" distinction
- intent-comparison: binary prompt, Poor quality — binary signal doesn't help because the task itself exceeds the model's capacity

The real question is whether to **further simplify** the binary prompts for basic models. For example, test-coherence's binary prompt includes a 4-item COHERENT pattern list. A 4B model may not reliably apply all 4 patterns simultaneously. A simpler "Does this test call the function under test and check a meaningful property of its output? yes/no" might have fewer FPs at the cost of fewer TPs.

This would require benchmarking to validate — which is the right approach per ADR-016.

### Noise vs. detection scope

The user asked: "Perhaps the noise dominates because what we're attempting to detect is not scoped properly?"

**This is exactly right for intent-comparison.** ICD's theoretical premise (multi-artifact triangulation catches what pairwise misses) is sound, but the practical execution produces noise because:
1. The detection scope (all symbols with ≥3 artifacts) is too broad — most symbols are correctly documented
2. The signal-to-noise ratio is inverted: in a well-maintained codebase, maybe 1-3% of symbols have cross-artifact contradictions, but the model flags 10-30%
3. The post-LLM filtering catches structural noise but can't catch hallucinated evidence (the dominant FP pattern)

**For the other 3 detectors**, the scope is appropriate:
- semantic-drift: scoped to key docs with code references — narrow, relevant
- test-coherence: scoped to test/impl function pairs — naturally bounded
- inline-comment-drift: scoped to functions with docstrings — naturally bounded, capped at 100

## Prioritized Recommendations

| Priority | Action | Expected Impact |
|----------|--------|-----------------|
| 1 | Add truncation notice to all LLM prompts | Reduces FPs from partial-code reasoning |
| 2 | Benchmark docs-drift LLM path on existing ground truth repos | Fills the unknown quality gap |
| 3 | Consider auto-disable for POOR-rated model×detector combos | Prevents silent noise output |
| 4 | Increase binary context limits from 1500→2500 for test-coherence | Reduces truncation-driven FPs |
| 5 | Add two-pass verification for ICD (if continuing to invest in it) | Targets dominant hallucination FP |
| 6 | Add per-scan cap to semantic-drift (e.g., 50) | Prevents cost runaway |
