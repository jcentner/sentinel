# Glossary

Key terms used throughout the Sentinel documentation and codebase.

| Term | Definition |
|------|-----------|
| **Detector** | A module that scans the repo and produces candidate findings. Can be deterministic (linter wrapper), heuristic (git analysis), or LLM-assisted. |
| **Finding** | A single candidate issue produced by a detector. Has a category, severity, confidence, evidence, and location. |
| **Evidence** | Supporting data for a finding — code snippets, doc excerpts, lint output, git history, diffs. |
| **Morning report** | The primary output: a concise, reviewable summary of findings from the latest run. |
| **Docs drift** | An inconsistency between documentation and code, configuration, or other documentation. |
| **Fingerprint** | A stable hash identifying a unique finding for deduplication across runs. |
| **Suppression** | A user decision to mark a finding as a false positive, preventing it from appearing in future reports. |
| **LLM Judge** | The model (via a configured provider) that evaluates candidate findings in context and decides severity, confidence, and issue-worthiness. |
| **Context Gatherer** | The retrieval component that pulls relevant code, docs, and history for each finding before LLM judgment. |
| **Model provider** | An implementation of the `ModelProvider` protocol that handles all model interaction (generation, embedding, health checks). Shipped providers: `OllamaProvider` (default, local), `OpenAICompatibleProvider` (Azure OpenAI, OpenAI, vLLM, LM Studio), and `AzureAIProvider` (Azure AI Foundry via `azure-ai-inference` SDK). See ADR-010. |
| **Provider protocol** | The `ModelProvider` Python protocol defining `generate()`, `embed()`, and `check_health()`. All LLM consumers call the protocol, not a specific backend. |
| **Capability tier** | A label (`basic`, `standard`, `advanced`) on a detector indicating the minimum model class it needs. `basic` = 4B+ local, `standard` = 9B+ or small cloud, `advanced` = frontier cloud. Informational, not enforced. |
| **OpenAI-compatible provider** | Any API endpoint that implements the OpenAI `/v1/chat/completions` and `/v1/embeddings` contract. Covers OpenAI direct, Azure OpenAI, vLLM, LM Studio, Together, etc. |
| **Tier 1 detector** | Deterministic detector: lint, test, grep, dependency audit. Cheap and reliable. Includes lint-runner (ruff/Python), eslint-runner (ESLint/Biome for JS/TS), go-linter (golangci-lint for Go), rust-clippy (cargo clippy for Rust), todo-scanner, and dep-audit. |
| **Tier 2 detector** | Heuristic detector: git hotspots, churn, complexity. Model-free, statistical. |
| **Tier 3 detector** | LLM-assisted detector: model reads code + context and judges. Higher value but higher false positive rate. |
| **Run** | A single execution of Sentinel against a repo scope (full, incremental, or targeted). |
| **State store** | SQLite database tracking findings, suppressions, and run history across runs. |
| **Approval gate** | The human review step between finding a candidate issue and creating a GitHub issue. Nothing external happens without approval. |
| **Persistence** | Tracking how many times a finding (by fingerprint) has appeared across runs. Recurring findings gain confidence. |
| **Occurrence count** | The number of scan runs in which a specific finding fingerprint has been seen. Displayed as ♻️ ×N in reports. |
| **Git hotspot** | A file with unusually high commit frequency (churn), identified by statistical outlier analysis on git log data. |
| **GitHub issue creation** | The optional Phase 5 feature that creates GitHub issues from human-approved findings. Requires explicit approval and a GitHub token. |
| **Incremental scan** | A scan that only runs detectors on files with committed changes since the last completed run. Uses git commit SHA comparison (`git diff`). Falls back to a full scan if no prior run exists or the prior SHA is unreachable. |
| **LLM log** | Structured SQLite table (`llm_log`) that records every LLM interaction — prompts, responses, token counts, timing, and verdicts — for statistical analysis and accuracy review. |
| **Clustering** | Report-layer feature that groups related findings to reduce visual noise. Two strategies: *pattern clustering* (same detector + normalized title, regardless of directory) and *directory clustering* (3+ findings sharing a parent directory collapsed into a `<details>` block). Pattern clusters are applied first, then directory clusters on remaining findings. Distinct from deduplication. |
| **FindingCluster** | A dataclass representing a group of related findings that share a common directory path. Used only in report generation. |
| **Targeted scan** | A scan limited to specific file paths provided by the user. Detectors only examine the named files. |
| **Ground truth** | A TOML manifest (`ground-truth.toml`) defining expected true positives for a test repo, used by `sentinel eval` to measure detector precision and recall. |
| **Evaluation (eval)** | The precision/recall measurement framework that compares scan findings against a ground-truth manifest. Accessible via `sentinel eval <repo>`. |
| **Migration framework** | The ordered schema migration system in `store/db.py` that upgrades the SQLite database from v1 to v7 with versioned DDL scripts applied on database open. |
| **Embedding index** | A pre-computed set of vector embeddings for repo file chunks, stored in the SQLite `chunks` table. Used by the context gatherer to find semantically relevant code for each finding. |
| **Chunk** | A contiguous segment of a source file (default: 50 lines with 10-line overlap) stored with its embedding vector for semantic search. |
| **Cosine similarity** | The similarity metric used to compare embedding vectors (dot product / product of magnitudes). Values range from -1 (opposite) to 1 (identical). |
| **Serve mode** | Running Sentinel as a local web server (`sentinel serve`) providing a browser-based review and management interface. Reads the same SQLite database as the CLI. |
| **Night Watch** | The design system used by the Sentinel web UI. A dark-first theme with warm amber accent on deep navy-black, Bricolage Grotesque display font, JetBrains Mono code font, and a light mode toggle. |
| **Theme toggle** | A dark/light mode switch in the web UI header. Preference is stored in `localStorage` and applied via inline script before render to prevent flash-of-wrong-theme. |
| **htmx** | A JavaScript library used for progressive enhancement in the web UI. Enables inline actions (approve/suppress update the status badge without a full page reload). Loaded from a vendored static file, no build step required. |
| **Annotation** | A user note attached to a finding for triage context. Stored in the `annotations` table; displayed on the finding detail page with add/delete via htmx. |
| **scan-all** | CLI command (`sentinel scan-all`) that scans multiple repositories into a shared database in one invocation. Each repo is scanned independently; partial failures do not abort the batch (exit code 2 on partial failure). |
| **doctor** | CLI command (`sentinel doctor`) that checks availability of external tools (git, ruff, pip-audit, eslint, biome, golangci-lint, cargo, ollama) and optional Python packages. Supports `--json-output`. |
| **init** | CLI command (`sentinel init <repo>`) that scaffolds a new repo for Sentinel: creates `sentinel.toml` with documented defaults, `.sentinel/` directory, and `.gitignore` entry. |
| **Semantic drift** | A semantic inconsistency between documentation prose and the source code it describes. Unlike broken links (structural), semantic drift means the docs describe outdated behavior, wrong parameters, or features that no longer exist. Detected by the `semantic-drift` detector via LLM comparison. |
| **Section pairing** | The process of matching a documentation section (heading-delimited) with the source file(s) it references. The `semantic-drift` detector uses name-matching: file paths in backticks, prose paths, markdown links, and backtick-wrapped symbol names. |
| **Entry-points discovery** | Python's `importlib.metadata.entry_points` mechanism for discovering third-party detector packages. Packages declare a `sentinel.detectors` entry point group in their `pyproject.toml`. On startup, Sentinel discovers and imports these modules, triggering auto-registration via `__init_subclass__`. See ADR-012. |
| **Finding cluster synthesis** | A post-judge pipeline step that feeds clusters of related findings to the LLM and asks for root-cause analysis, redundancy identification, and actionable recommendations. Collapses many symptoms into fewer root causes. Requires `standard+` model capability. |
| **Intent comparison** | A class of LLM analysis that feeds multiple artifacts about the same function (docstring, test, doc section, code body) simultaneously to identify contradictions between any pair. Goes beyond single-pair comparison (doc↔code) to multi-artifact triangulation. |
| **Architecture drift** | Divergence between documented architecture (component descriptions, data flow diagrams, ADR constraints) and actual code structure (import graph, module boundaries). Detected by comparing architecture docs against the real dependency graph. |
| **Setup flow** | The first-run configuration experience where users select detectors, choose a model/provider, and generate a `sentinel.toml`. See OQ-011. |
| **Init profile** | A named preset for `sentinel init --profile <name>` that pre-configures `sentinel.toml` with sensible defaults for common scenarios: `minimal` (deterministic-only, no model needed), `local` (Ollama + all detectors), `cloud` (OpenAI-compatible provider). |
| **Azure AI provider** | The `AzureAIProvider` class implementing the `ModelProvider` protocol using the `azure-ai-inference` SDK. Supports Azure AI Foundry endpoints with model-name routing, native token tracking, and configurable retry. Configured via `provider = "azure"` + `api_base` + `api_key` in `sentinel.toml`. |
