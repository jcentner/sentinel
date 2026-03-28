# ADR-005: Docs-drift as a first-class detector category

**Status**: Accepted
**Date**: 2026-03-28
**Deciders**: Project founder

## Context

Documentation inconsistency is one of the most common and hardest-to-catch problems in active codebases. Existing lint tools can't detect semantic drift between docs and code. This is also a uniquely good use case for small LLMs because it's a **comparison task** (do these two texts agree?) rather than open-ended generation.

## Decision

Docs-drift detection is a named, first-class detector category — not a generic "suspicious pattern" subcategory. It gets its own detector with specific sub-patterns:

1. **README ↔ actual scripts/deps**: Install instructions vs. package.json
2. **API docs ↔ code**: JSDoc/OpenAPI vs. actual function signatures
3. **Config docs ↔ config schema**: Documented options vs. actual defaults
4. **CHANGELOG ↔ git history**: Entries vs. real commits
5. **Stale references**: Docs referencing files/functions that no longer exist
6. **Architecture docs ↔ import graph**: Documented data flow vs. reality
7. **Cross-doc contradictions**: Doc A says PostgreSQL, Doc B says SQLite

### Method

1. **Deterministic extraction**: Parse doc structure, extract code blocks, file references, function names, CLI examples. Parse code AST for exports, signatures, config schemas.
2. **LLM comparison**: For each (doc-claim, code-reality) pair, ask: "Does this documentation accurately describe this code?"
3. **Confidence scoring**: Deterministic mismatches (dead reference, missing file) = high confidence. Semantic judgment = lower confidence, flagged for human review.

## Consequences

**Positive**:
- Immediately useful on day one for any repo with docs
- Concrete, measurable, easy to explain in a writeup
- Natural fit for small LLM capabilities (comparison, not invention)
- Differentiator vs. existing tools (only jstar-code-review has a "documentation-drift" tag, and it's PR-scoped)

**Negative**:
- Requires non-trivial extraction logic per doc format
- Cross-doc and architecture-drift patterns are harder to implement
- May need doc-format-specific parsers (Markdown, OpenAPI, JSDoc)

## Alternatives considered

- **Generic "consistency check" category**: Too vague, loses the specificity that makes this valuable. The detector should know what it's comparing.
- **Defer to Phase 2**: Rejected because docs-drift is one of the most compelling and tractable detector categories. Shipping without it weakens the MVP pitch.
