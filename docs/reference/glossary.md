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
