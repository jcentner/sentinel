# System Architecture Overview

> **Status**: Active — implemented in Phase 1 MVP. See [VISION-REVISION-001](../vision/VISION-REVISION-001.md) for pipeline order changes.

## High-level data flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         Sentinel Run                             │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐     │
│  │  Detectors   │───▶│  Findings   │───▶│  Context Gatherer │     │
│  │ (deterministic,│   │  (raw        │   │  (embeddings +    │     │
│  │  heuristic)   │   │   candidates)│   │   reranker)       │     │
│  └─────────────┘    └─────────────┘    └──────────────────┘     │
│                                               │                  │
│                                               ▼                  │
│                                        ┌──────────────┐          │
│                                        │  LLM Judge    │          │
│                                        │  (Ollama)     │          │
│                                        └──────────────┘          │
│                                               │                  │
│                                               ▼                  │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐          │
│  │  State Store │◀──▶│  Deduper /   │◀──│  Judged       │          │
│  │  (SQLite)    │    │  Clusterer   │   │  Findings     │          │
│  └─────────────┘    └─────────────┘    └──────────────┘          │
│                           │                                      │
│                           ▼                                      │
│                    ┌─────────────┐    ┌──────────────┐           │
│                    │  Morning     │───▶│  Human        │           │
│                    │  Report      │    │  Approval     │           │
│                    └─────────────┘    └──────────────┘           │
│                                               │                  │
│                                               ▼                  │
│                                        ┌──────────────┐          │
│                                        │  GitHub       │          │
│                                        │  Issue Creator│          │
│                                        └──────────────┘          │
└──────────────────────────────────────────────────────────────────┘
```

## Component responsibilities

### 1. Detectors

Detectors produce raw candidate findings. They come in three tiers:

**Tier 1 — Deterministic**: Lint output, test failures, TODO/FIXME scans, dependency audit, SQLFluff, Semgrep rules, ast-grep patterns. Cheap, reliable, no model needed.

**Tier 2 — Heuristic**: Git-history hotspots, churn rate, complexity metrics, dead-code analysis via tree-sitter reachability. Also model-free.

**Tier 3 — LLM-assisted**: The model reads code + context and judges whether something is problematic. This is where the model earns its keep, but also where false positives live.

The MVP should be **mostly Tier 1 + 2, with the LLM as the judgment/summarization layer**, not the primary signal source.

Every detector produces a `Finding` conforming to the [Detector Interface](detector-interface.md).

### 2. Context Gatherer

For each candidate finding, retrieves supporting context:
- Relevant code (via embeddings search or tree-sitter symbol extraction)
- Related tests, docs, config
- Git history for the affected area

Uses local embeddings (e.g., Qwen3-Embedding-0.6B) + reranker (e.g., bge-reranker-v2-m3) to select the most relevant context windows.

### 3. LLM Judge

A small local model (via Ollama) that receives each finding + its gathered context and answers:
- Is this likely real?
- What evidence supports it?
- How severe is it?
- What GitHub issue should be opened?

This is a structured judgment task, not open-ended generation. The model doesn't invent findings — it evaluates candidates produced by deterministic/heuristic detectors.

### 4. State Store (SQLite)

Persistent state across runs. Tracks:
- Previous findings (fingerprinted for dedup)
- Suppression flags (user-marked false positives)
- Run history (when, what scope, how many findings)
- Finding lifecycle (new → confirmed → suppressed → resolved)

This is a Phase 1 design decision, not Phase 2. Deduplication is a trust feature.

### 5. Deduper / Clusterer

Compares new findings against state store to:
- Skip previously suppressed findings
- Group related findings (e.g., same pattern across multiple files)
- Track finding persistence (same issue found on 3 consecutive runs = higher confidence)

### 6. Morning Report

Primary output. Markdown formatted, designed to be scannable in under 2 minutes:
- One line per finding with severity, confidence, category
- Expandable evidence sections
- Clear approve/suppress actions per finding
- Summary statistics (new, recurring, resolved since last run)

### 7. GitHub Issue Creator

Takes approved findings and creates GitHub issues. Only runs after explicit human approval. Does not plan implementation, does not open PRs.

## What runs where

| Component | Runs on | Resource profile |
|-----------|---------|-----------------|
| Detectors | CPU | Lightweight — linters, grep, tree-sitter |
| Embeddings | GPU (8 GB VRAM) | Qwen3-Embedding-0.6B via Ollama |
| Reranker | GPU or CPU | bge-reranker-v2-m3 |
| LLM Judge | GPU (8 GB VRAM) | Qwen3.5 4B Q4_K_M via Ollama (~2.8 GB) |
| State Store | Disk | SQLite, negligible |
| Report | CPU | Markdown generation |

## Trigger modes

- **Cron**: Nightly scheduled run (primary use case)
- **Git hook**: On last push of the day or on specific events
- **Manual**: On-demand CLI invocation
- **Watch**: File-system watcher for continuous development (future)

## Scope per run

- **Default**: Changed files since last run (efficient, incremental)
- **Full**: Entire repository (periodic deep scan)
- **Targeted**: Specific paths or detector categories (diagnostic)
