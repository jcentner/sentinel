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

### OQ-019: Benchmark drill-down UI for power users
**Status**: Partially Resolved
**Priority**: Medium
**Context**: The `llm_log` table already records full prompt, response, model, timing, and verdict for every LLM call. Power users want to inspect exactly what prompt was sent, what context was included, and what the model output for specific benchmark runs — to make informed model selection decisions. This is especially valuable when comparing two models: "why did model A flag this as needs_review but model B said it's fine?"
**Current thinking**: Surface this in the web UI as a drill-down from the compatibility matrix. Click a quality rating cell → see individual benchmark findings with expandable prompt/response detail. The data already exists in `llm_log`; the work is UI/routing. Consider also a CLI `sentinel benchmark --show-detail` for terminal users.
**Resolution**: LLM call log viewer shipped at `/llm-log` with detector/model/verdict/run filters, pagination, and expandable prompt/response detail. Linked from nav bar and detectors page. Remaining: drill-down from compatibility matrix quality rating cells, CLI `sentinel benchmark --show-detail`, and making benchmark runs write to `llm_log` (currently benchmark bypasses DB).

### OQ-008: How should semantic docs-drift pair doc sections with code?
**Status**: Resolved
**Priority**: High
**Context**: The planned semantic docs-drift detector needs to feed the LLM a documentation section alongside the code it describes. The pairing strategy is the hard design problem: should it use heading-based chunking of docs, then match to code via symbol names? File-proximity heuristics? Embedding similarity? A bad pairing strategy will produce noise (comparing unrelated doc + code).
**Current thinking**: Start simple — match README sections to files/functions mentioned by name in the section text. Use tree-sitter to extract function signatures from the referenced file. Feed (doc section + function signatures) to the LLM and ask for a binary "in sync / needs review" signal. Expand to embedding-based pairing later if the name-matching approach misses important pairs.
**Resolution**: Heading-based chunking + name-matching pairing. Sections are delimited by h1–h3 headings. References extracted via backtick paths, prose paths, markdown links, and backtick-wrapped symbol names. Python `ast` module extracts function/class signatures; regex-based extraction for other languages. Binary LLM output ("needs_review" / "in_sync"). Embedding-based pairing deferred. Implemented in `src/sentinel/detectors/semantic_drift.py`.

### OQ-009: Can a 4B model reliably deliver test-code coherence signals?
**Status**: Partially Resolved (implementation shipped, real-world validation pending)
**Priority**: Medium
**Context**: Test-code coherence requires the LLM to understand implementation intent and whether a test meaningfully validates it. This is harder than docs-drift (which is mostly string comparison). A 4B model may not have enough capacity. The 9B model fits in 8 GB VRAM but is slower. With provider abstraction (ADR-010), cloud models (Haiku 4.5, GPT-5.4-nano) are also available as alternatives — the `standard` capability tier may be the right starting point for this detector.
**Resolution**: Detector implemented as `test-coherence` in `src/sentinel/detectors/test_coherence.py`. Uses 4B model by default with constrained binary prompts (one test function + one implementation function, binary "needs_review" / "coherent" output). Pairing via naming convention (`test_foo.py` → `foo.py`) with import-analysis fallback. Function-level matching via Python `ast` with underscore-boundary prefix matching. Real-world precision validation pending — if 4B proves insufficient for this task, the provider abstraction (Phase 7) enables seamless fallback to 9B or cloud models.

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

### OQ-013: How should the eval system measure judge and synthesis quality?
**Status**: Resolved (→ ADR-014, Session 25)
**Priority**: High
**Context**: The eval system runs with `skip_judge=True` in both `sentinel eval` and CI tests. The judge, synthesis, and full pipeline — the most business-critical paths — have zero eval coverage. Ground truth only validates raw detector output, not post-judge or post-dedup output. You can't answer "does the morning report contain the right things?" with the current system.
**Current thinking**: Several options, not mutually exclusive: (1) Record actual LLM responses for the sample-repo fixture and replay them in CI via a mock provider — tests prompt engineering regressions without a live model. (2) Add `--full-pipeline` mode to `eval` that includes judge/dedup/synthesis. (3) Per-detector precision/recall breakdown in `EvalResult` to pinpoint regressions. The replay approach is highest ROI — it creates a deterministic test of the judge path.
**Resolution**: All three approaches implemented. `sentinel eval --full-pipeline` runs with `skip_judge=False`. `--replay-file` uses ReplayProvider (pre-recorded responses matched by prompt hash) for deterministic CI testing. `--record-responses` wraps a live provider to capture responses for later replay. Per-detector precision/recall breakdown in every eval. Judge metrics (confirmation rate, rejection rate, wrongly-rejected TPs) in full-pipeline mode. See ADR-014.

### OQ-014: Should there be a ground truth corpus from real-world repos?
**Status**: Resolved (Session 27)
**Priority**: Medium
**Context**: The 30-item sample-repo ground truth is self-fulfilling — the fixture was designed to match what detectors can detect. 100% precision/recall proves detectors find planted items, not real bugs. The tsgbuilder benchmark (134 findings from a production repo) has no ground truth, so it only measures counts and timing. No LLM-assisted detectors (`semantic-drift`, `test-coherence`) have ground truth at all.
**Resolution**: First real-world ground truth created: `benchmarks/ground-truth/pip-tools.toml` — 50 findings from jazzband/pip-tools, 19 individually annotated, 25 assumed-TP (complexity + todo with spot-check validation). Overall precision 76% (38/50 TP). More importantly, identified 5 actionable FP patterns (TD-040, TD-041, TD-042) that explain 100% of the false positives. Future work: annotate more repos from `docs/reference/test-repos.md`, add a "clean repo" fixture for direct FP rate measurement.

### OQ-015: What data lifecycle strategy should the SQLite store use?
**Status**: Resolved (TD-020, Session 23)
**Priority**: High
**Context**: No mechanism controls data growth (TD-020). `llm_log` stores full prompt+response text per LLM call (~50+ MB/year per repo). `finding_persistence` grows monotonically. The historical fingerprint query (TD-015) loads all fingerprints ever seen. There's no `sentinel prune`, no retention policy, no VACUUM.
**Resolution**: Implemented via TD-020 and TD-015 fixes. `prune_old_data()` in `store/findings.py` deletes old llm_log, annotations, findings, runs, and persistence entries with configurable `retention_days` (default 90). `sentinel prune --older-than N` CLI command for manual cleanup. `get_known_fingerprints()` time-bounded to retention window. VACUUM runs after deletion. Suppressions (user decisions) are preserved.

### OQ-016: Should the generate() protocol evolve to support message lists?
**Status**: Open
**Priority**: Low
**Context**: The `ModelProvider.generate(prompt, system=...)` interface uses a flat prompt string as the lowest common denominator. This works today because all callers construct single-turn prompts. But it closes the door on multi-turn context (few-shot examples as assistant turns), tool use / function calling, and multimodal inputs. The system prompt kwarg is a partial mitigation.
**Current thinking**: Not urgent — no current caller needs it. Plan for either `generate_chat(messages: list[dict])` or evolving `prompt` to `prompt: str | list[dict[str, str]]` when the first multi-turn use case arrives. Document as a known limitation until then.

### OQ-011: How should the first-run setup flow guide detector and model selection?
**Status**: Resolved
**Priority**: High
**Context**: Users need to configure which detectors to run and what model to use. Currently `sentinel init` creates a basic `sentinel.toml` with defaults, but doesn't guide the user through detector selection or model recommendation. The user pointed out that explicit setup-time detector selection negates the risk of silently skipping detectors based on model capability — the user chooses what they want upfront.
**Resolution**: `sentinel init` enhanced with three mechanisms: (1) `--profile` flag with `minimal` (heuristic-only, no LLM), `standard` (all detectors + basic LLM), and `full` (all detectors + enhanced analysis) presets; (2) `--detectors` flag for explicit comma-separated selection; (3) `--list-detectors` to show available detectors with tiers. Generated config includes `enabled_detectors` list with detector catalog as comments. Default (no flags): all detectors enabled.

### OQ-012: Should different detectors be able to use different models/providers?
**Status**: Resolved (→ ADR-013, implementation in config.py, provider.py, runner.py)
**Priority**: Medium
**Context**: The user asked: "perhaps we can allow different models for different detectors in the same config?" This would let users run cheap deterministic-adjacent detectors on a local 4B model while routing advanced detectors (intent-drift, arch-drift) to a cloud model like gpt-5.4-nano. Currently, one provider/model pair is used for all LLM calls in a scan.
**Resolution**: Implemented via `[sentinel.detector_providers.<name>]` config sections. Each section overrides `provider`, `model`, `api_base`, `api_key_env`, and/or `model_capability` for a specific detector. Empty fields inherit from the global config. The runner resolves per-detector providers with caching (no duplicate connections for identical configs) and restores the global context after each per-detector run. Judge and synthesis always use the global provider.

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

### OQ-017: Should GitHub integration support OAuth device flow?
**Status**: Resolved
**Priority**: Medium
**Context**: Currently, GitHub issue creation requires a pre-created PAT set as `SENTINEL_GITHUB_TOKEN`. This works but requires manual token management. OAuth device flow (`https://github.com/login/device`) would let users authenticate from the web UI or CLI without managing tokens manually — more convenient, especially for the web UI triage workflow. Considerations: (1) OAuth device flow requires registering a GitHub App or OAuth App, which adds a deployment dependency; (2) PATs are simpler for scripted/automated use; (3) OAuth tokens expire and need refresh logic; (4) Privacy: OAuth sends the user to GitHub's auth page, which is acceptable since GitHub integration is already opt-in.
**Resolution**: PAT-only. The complexity of registering a GitHub App, handling token expiry/refresh, and maintaining OAuth flow code is not justified for the current scope. PATs are simple, well-understood, and work for both interactive and automated use. If OAuth demand emerges from users, it can be added later without breaking the PAT path.

### OQ-018: Should project documentation live in the GitHub wiki?
**Status**: Resolved
**Priority**: Low
**Context**: The `docs/` directory currently holds all project documentation (architecture, ADRs, reference, vision). Moving to the GitHub wiki would make docs more discoverable for new contributors and provide a nicer browsing experience. However: (1) wiki content is a separate git repo, complicating doc-code atomicity (can't update docs and code in the same commit); (2) wikis don't support PRs, so doc changes can't be reviewed; (3) the current in-repo docs are scanned by Sentinel itself (docs-drift detector), which would break if docs moved to a wiki; (4) in-repo docs are searchable by AI agents and Copilot. GitHub wiki is better for user-facing guides and tutorials that aren't tightly coupled to code.
**Resolution**: Hybrid approach. Architecture, ADRs, reference, and vision docs stay in-repo (they change atomically with code and are scanned by Sentinel's docs-drift detector). The GitHub wiki is used for user-facing content: installation guides, FAQ, tutorials, and getting-started walkthroughs — content that doesn't need atomic commits with code. Cross-links between wiki and in-repo docs where relevant.
