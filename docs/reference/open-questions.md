# Open Questions

Tracked questions that need resolution before or during implementation. Each question should eventually result in either an ADR, a roadmap decision, or a "resolved" note.

## Format

```
### OQ-NNN: Question title
**Status**: Open | Resolved (→ ADR-NNN / decision)
**Priority**: High | Medium | Low
**Context**: Why this matters
**Current thinking**: Best guess if any
**Resolution**: (filled when resolved)
```

## Open

### OQ-002: What is the report delivery mechanism?
**Status**: Open
**Priority**: Medium
**Context**: The morning report needs to be scannable in under 2 minutes. Options: plain markdown file, terminal output, local web UI, notification (email/Slack/desktop). The approve/suppress UX depends on this choice.
**Current thinking**: Start with markdown file + CLI for approve/suppress. Web UI is Phase 2+.

### OQ-003: How should finding fingerprints be computed?
**Status**: Resolved (→ implementation in `src/sentinel/core/dedup.py`)
**Priority**: Medium
**Context**: Deduplication requires a stable fingerprint per finding. If a file moves or line numbers shift, the fingerprint shouldn't change for the same conceptual finding. Hash over (detector, category, normalized-content) rather than (file, line) seems right but needs design.
**Current thinking**: Hash of (detector_name, category, file_path, key_content_normalized). Accept that file renames break dedup and handle with a "similar finding" heuristic.
**Resolution**: SHA256 hash of `(detector, category, file_path, normalized_content)`, truncated to 16 hex chars. Detector-specific normalization: dep-audit uses `vuln_id:package`, lint-runner uses `rule:file_path:title`, others use the finding title. Line number changes do not break fingerprints. File renames do break fingerprints (acceptable for MVP).

### OQ-004: What embedding model and vector store should be used?
**Status**: Open
**Priority**: Medium
**Context**: Context gathering requires embedding the repo and querying for relevant code/docs per finding. Qwen3-Embedding-0.6B is the current recommendation. Vector store options: SQLite-vec (minimal), LanceDB, Qdrant local.
**Current thinking**: SQLite-vec to keep the single-dependency story clean. Evaluate if it's sufficient before adding another store.

### OQ-005: Should Sentinel support multi-repo in MVP?
**Status**: Open
**Priority**: Low
**Context**: The brainstorm mentions multi-repo as Phase 3. But the architecture choices made now (state store schema, config format) should not make multi-repo painful later.
**Current thinking**: Design for single repo in MVP but use repo-scoped state (database per repo or repo ID in tables) so multi-repo is a natural extension.

### OQ-006: How should the SQL/performance anti-pattern detector work?
**Status**: Open
**Priority**: Low
**Context**: Detecting queries that should use CTEs, N+1 patterns, etc. SQLFluff handles SQL style linting. Semantic anti-patterns (CTE suggestions, cross-file N+1) require understanding intent.
**Current thinking**: Phase 2. Build as a pluggable detector: SQLFluff for deterministic SQL lint, LLM-assisted prompt for semantic suggestions. Don't build a SQL parser.

## Resolved

### OQ-001: What language should Sentinel itself be written in?
**Status**: Resolved (→ ADR-007)
**Resolution**: Python. See ADR-007 for full rationale.

### OQ-007: What eval criteria should be defined before building?
**Status**: Resolved (→ ADR-008)
**Priority**: High
**Context**: Without measurable criteria, we can't write an honest blog post or evaluate whether Sentinel is working. Need to define metrics before writing code.
**Current thinking**: Precision at k (of the top-k findings, how many are real?), false positive rate per run, time-to-review the morning report, findings-per-run that lead to actual issues.
**Resolution**: Formalized as ADR-008. Six metrics defined: precision@k (≥70%), FP rate (<30%), review time (<2min), findings→issues (track only), detector coverage (≥3 categories), repeatability (100% for deterministic).
