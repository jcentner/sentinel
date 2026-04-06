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
| **LLM Judge** | The local model (via Ollama) that evaluates candidate findings in context and decides severity, confidence, and issue-worthiness. |
| **Context Gatherer** | The retrieval component that pulls relevant code, docs, and history for each finding before LLM judgment. |
| **Tier 1 detector** | Deterministic detector: lint, test, grep, dependency audit. Cheap and reliable. |
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
| **Clustering** | Report-layer feature that groups 3+ findings sharing a parent directory into a collapsed `<details>` block. Reduces visual noise without hiding findings. Distinct from deduplication. |
| **FindingCluster** | A dataclass representing a group of related findings that share a common directory path. Used only in report generation. |
| **Targeted scan** | A scan limited to specific file paths provided by the user. Detectors only examine the named files. |
| **Ground truth** | A TOML manifest (`ground-truth.toml`) defining expected true positives for a test repo, used by `sentinel eval` to measure detector precision and recall. |
| **Evaluation (eval)** | The precision/recall measurement framework that compares scan findings against a ground-truth manifest. Accessible via `sentinel eval <repo>`. |
| **Migration framework** | The ordered schema migration system in `store/db.py` that upgrades the SQLite database from v1 to v5 with versioned DDL scripts applied on database open. |
| **Embedding index** | A pre-computed set of vector embeddings for repo file chunks, stored in the SQLite `chunks` table. Used by the context gatherer to find semantically relevant code for each finding. |
| **Chunk** | A contiguous segment of a source file (default: 50 lines with 10-line overlap) stored with its embedding vector for semantic search. |
| **Cosine similarity** | The similarity metric used to compare embedding vectors (dot product / product of magnitudes). Values range from -1 (opposite) to 1 (identical). |
| **Serve mode** | Running Sentinel as a local web server (`sentinel serve`) providing a browser-based review and management interface. Reads the same SQLite database as the CLI. |
| **Night Watch** | The design system used by the Sentinel web UI. A dark-first theme with warm amber accent on deep navy-black, Bricolage Grotesque display font, JetBrains Mono code font, and a light mode toggle. |
| **Theme toggle** | A dark/light mode switch in the web UI header. Preference is stored in `localStorage` and applied via inline script before render to prevent flash-of-wrong-theme. |
| **htmx** | A JavaScript library used for progressive enhancement in the web UI. Enables inline actions (approve/suppress update the status badge without a full page reload). Loaded from a vendored static file, no build step required. |
