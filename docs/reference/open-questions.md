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

### OQ-008: How should semantic docs-drift pair doc sections with code?
**Status**: Resolved
**Priority**: High
**Context**: The planned semantic docs-drift detector needs to feed the LLM a documentation section alongside the code it describes. The pairing strategy is the hard design problem: should it use heading-based chunking of docs, then match to code via symbol names? File-proximity heuristics? Embedding similarity? A bad pairing strategy will produce noise (comparing unrelated doc + code).
**Current thinking**: Start simple — match README sections to files/functions mentioned by name in the section text. Use tree-sitter to extract function signatures from the referenced file. Feed (doc section + function signatures) to the LLM and ask for a binary "in sync / needs review" signal. Expand to embedding-based pairing later if the name-matching approach misses important pairs.
**Resolution**: Heading-based chunking + name-matching pairing. Sections are delimited by h1–h3 headings. References extracted via backtick paths, prose paths, markdown links, and backtick-wrapped symbol names. Python `ast` module extracts function/class signatures; regex-based extraction for other languages. Binary LLM output ("needs_review" / "in_sync"). Embedding-based pairing deferred. Implemented in `src/sentinel/detectors/semantic_drift.py`.

### OQ-009: Can a 4B model reliably deliver test-code coherence signals?
**Status**: Open
**Priority**: Medium
**Context**: Test-code coherence requires the LLM to understand implementation intent and whether a test meaningfully validates it. This is harder than docs-drift (which is mostly string comparison). A 4B model may not have enough capacity. The 9B model fits in 8 GB VRAM but is slower. With provider abstraction (ADR-010), cloud models (Haiku 4.5, GPT-5.4-nano) are also available as alternatives — the `standard` capability tier may be the right starting point for this detector.
**Current thinking**: Try 4B first with carefully constrained prompts (one test function + one implementation function, binary output). If precision is too low, fall back to 9B or cloud provider. A `standard`-tier variant with structured explanations can be built after Phase 7 (provider abstraction).

### OQ-005: Should Sentinel support multi-repo in MVP?
**Status**: Resolved
**Priority**: Low
**Context**: The brainstorm mentions multi-repo as Phase 3. But the architecture choices made now (state store schema, config format) should not make multi-repo painful later.
**Current thinking**: Design for single repo in MVP but use repo-scoped state (database per repo or repo ID in tables) so multi-repo is a natural extension.
**Resolution**: `sentinel scan-all REPO1 REPO2 ... --db shared.db` command scans multiple repos into a shared database. The DB stores repo_path per run, so runs from different repos coexist naturally. Web UI and history command display all repos. Single-repo `sentinel scan` remains the primary interface for per-repo use.

### OQ-006: How should the SQL/performance anti-pattern detector work?
**Status**: Open
**Priority**: Low
**Context**: Detecting queries that should use CTEs, N+1 patterns, etc. SQLFluff handles SQL style linting. Semantic anti-patterns (CTE suggestions, cross-file N+1) require understanding intent.
**Current thinking**: Phase 2. Build as a pluggable detector: SQLFluff for deterministic SQL lint, LLM-assisted prompt for semantic suggestions. Don't build a SQL parser.

### OQ-010: What is the right ModelProvider protocol surface?
**Status**: Resolved (→ ADR-010, implementation in `src/sentinel/core/provider.py`)
**Priority**: High
**Context**: ADR-010 defines the vision for a pluggable model provider, but the exact protocol surface needs to be finalized during implementation. Key questions: Should `generate()` accept a messages list (OpenAI-style) or a flat prompt string (Ollama-style)? How should streaming be handled (if at all)? Should provider-specific options (e.g., Ollama's `think`, `num_ctx`) pass through as kwargs or a typed options dict? How does `embed()` handle models that don't support embedding (OpenAI text models)?
**Resolution**: `generate(prompt, *, system, temperature, max_tokens, num_ctx, json_output) → LLMResponse` takes a flat prompt string + optional system string (lowest common denominator). No streaming for v1. Provider-specific options mapped internally by each provider (e.g., Ollama adds `think: False`, `format: "json"`; OpenAI uses `response_format`). `embed(texts) → list[list[float]] | None` returns `None` when embedding is not supported or fails. `check_health() → bool` for connectivity checks. Single provider handles both generation and embedding. Factory function `create_provider(config)` dispatches on `config.provider` field. Two implementations: `OllamaProvider` (default, local) and `OpenAICompatibleProvider` (cloud/remote).

## Resolved

### OQ-001: What language should Sentinel itself be written in?
**Status**: Resolved (→ ADR-007)
**Resolution**: Python. See ADR-007 for full rationale.

### OQ-002: What is the report delivery mechanism?
**Status**: Resolved
**Priority**: Medium
**Context**: The morning report needs to be scannable in under 2 minutes. Options: plain markdown file, terminal output, local web UI, notification (email/Slack/desktop). The approve/suppress UX depends on this choice.
**Resolution**: Dual delivery — markdown file output (`report-{id}.md`) for archival/scripting, plus a browser-based web UI (`sentinel serve`) for interactive triage. The web UI provides full CLI workflow parity: run review with severity stat cards, finding detail with evidence, inline approve/suppress with reason, GitHub issue creation, and configurable scan form. Dark/light themes. See VISION-REVISION-002 (initial scope) and VISION-REVISION-004 (expanded scope with GitHub issues, scan form, design system).

### OQ-003: How should finding fingerprints be computed?
**Status**: Resolved (→ implementation in `src/sentinel/core/dedup.py`)
**Priority**: Medium
**Context**: Deduplication requires a stable fingerprint per finding. If a file moves or line numbers shift, the fingerprint shouldn't change for the same conceptual finding. Hash over (detector, category, normalized-content) rather than (file, line) seems right but needs design.
**Resolution**: SHA256 hash of `(detector, category, file_path, normalized_content)`, truncated to 16 hex chars. Detector-specific normalization: dep-audit uses `vuln_id:package`, lint-runner uses `rule:file_path:title`, others use the finding title. Line number changes do not break fingerprints. File renames do break fingerprints (acceptable for MVP).

### OQ-004: What embedding model and vector store should be used?
**Status**: Resolved (→ ADR-009)
**Priority**: Medium
**Context**: Context gathering requires embedding the repo and querying for relevant code/docs per finding. Qwen3-Embedding-0.6B is the current recommendation. Vector store options: SQLite-vec (minimal), LanceDB, Qdrant local.
**Resolution**: Configurable embedding model via Ollama `/api/embed` (default: nomic-embed-text). Vectors stored as float32 BLOBs in SQLite — no sqlite-vec extension needed. Brute-force cosine similarity in Python is fast enough for typical repo sizes. See ADR-009.

### OQ-007: What eval criteria should be defined before building?
**Status**: Resolved (→ ADR-008)
**Priority**: High
**Context**: Without measurable criteria, we can't write an honest blog post or evaluate whether Sentinel is working. Need to define metrics before writing code.
**Current thinking**: Precision at k (of the top-k findings, how many are real?), false positive rate per run, time-to-review the morning report, findings-per-run that lead to actual issues.
**Resolution**: Formalized as ADR-008. Six metrics defined: precision@k (≥70%), FP rate (<30%), review time (<2min), findings→issues (track only), detector coverage (≥3 categories), repeatability (100% for deterministic).
