# ADR-004: SQLite persistent state from day one

**Status**: Accepted
**Date**: 2026-03-28
**Deciders**: Project founder

## Context

The brainstorm places "issue deduplication over time" and "false-positive suppression" in Phase 2. However, these features require persistent state across runs, and retro-fitting a state store into a system designed without one creates unnecessary churn.

Deduplication is a trust feature. If the system reports the same issue every morning, the user stops reading the reports.

## Decision

Include a SQLite state store from Phase 1 / MVP. It tracks:
- Previous findings (fingerprinted by content hash for dedup)
- Suppression flags (user-marked false positives)
- Run history (timestamps, scope, finding counts)
- Finding lifecycle (new → confirmed → suppressed → resolved)

SQLite is the right choice because:
- Zero deployment complexity (single file)
- Works everywhere (WSL, native Linux, macOS)
- Fast enough for this workload (hundreds to low thousands of findings per run)
- Excellent tooling for inspection and debugging

## Consequences

**Positive**:
- Deduplication works from the first run onward
- False-positive suppression available immediately
- Enables trend analysis ("this issue has persisted for 5 runs")
- Run history provides a natural audit trail

**Negative**:
- Slightly more MVP work than pure stateless operation
- Need to design the schema thoughtfully upfront
- State file needs to be excluded from version control (`.gitignore`)

## Alternatives considered

- **Stateless / file-based**: Simpler initially but forces dedup to be retroactively bolted on. Rejected because dedup is table-stakes for user trust.
- **JSON file store**: Possible for small scale but lacks query capability and concurrent access safety. SQLite is equally portable and more capable.
- **PostgreSQL / other RDBMS**: Overkill. Adds deployment complexity for no benefit at this scale.
