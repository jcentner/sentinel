# ADR-009: Embedding-Based Context Gatherer

**Status**: Accepted
**Date**: 2026-04-05
**Deciders**: Autonomous builder (resolves OQ-004, resolves TD-001)

## Context

The LLM judge's quality is directly limited by the context it receives. The current context gatherer (TD-001) uses simple file-proximity heuristics: ±5 lines around the finding, a naming-convention test file lookup, and recent git log entries. This misses semantically related code such as callers, configuration, documentation, and cross-module dependencies.

OQ-004 asks: "What embedding model and vector store should be used?" The current thinking favors SQLite-vec to keep the single-dependency story, with Qwen3-Embedding-0.6B via Ollama.

After evaluating the options, a simpler approach achieves the same goal without a native extension dependency.

## Decision

Implement an opt-in embedding-based context gatherer with the following architecture:

### Embedding model

Use Ollama's `/api/embed` endpoint with a configurable model. Recommended: `nomic-embed-text` (137M params, 768 dimensions, fits easily in 8 GB VRAM alongside Qwen3.5:4b). The model is configurable via `embed_model` in `sentinel.toml`. Default is empty (embeddings disabled) — users opt in by setting the model name. This avoids requiring a model pull before first scan.

### Vector storage

Store embeddings as raw `float32` byte arrays in a new SQLite table within the existing sentinel database. No native extension (sqlite-vec) is needed — brute-force cosine similarity in Python is fast enough for typical repo sizes (<10K chunks).

This decision trades theoretical query performance for zero additional dependencies and keeps the single-file SQLite story intact. If repos grow beyond ~50K chunks, sqlite-vec can be adopted as a drop-in performance upgrade without schema changes.

### Chunking strategy

Split source files into chunks of ~50 lines with 10-line overlap. Each chunk records its file path, start/end lines, and a SHA256 hash of the content (for incremental re-indexing). Binary files, vendor directories, and build outputs are excluded.

### Index lifecycle

- **Build**: `sentinel index <repo>` CLI command, or automatically during `sentinel scan` when `embed_model` is configured.
- **Incremental**: Track content hash per chunk. Only re-embed files whose content has changed.
- **Query**: For each finding, embed the finding title + description, compute cosine similarity against all chunks, return top-5 as additional evidence.

### Graceful degradation

Embedding is opt-in. If `embed_model` is not configured, or Ollama is unavailable, or the index is empty, the system falls back to the existing file-proximity heuristic. No scan fails due to embedding issues.

### Configuration

New `sentinel.toml` fields:
- `embed_model`: string, default `""` (disabled). Set to a model name to enable embeddings.
- `embed_chunk_size`: integer, default `50` (lines per chunk).
- `embed_chunk_overlap`: integer, default `10` (overlap lines between chunks).

## Consequences

**Positive**: The LLM judge receives semantically relevant context — callers, configuration, related documentation — instead of just adjacent lines. This directly improves judgment quality and should reduce false positive rates.

**Negative**: First scan with embeddings requires indexing the repo (one-time cost, proportional to repo size). Each finding query adds latency for similarity computation. Embedding model must be pulled separately via Ollama.

**Neutral**: The embedding index adds ~50-200 MB to the sentinel database for a typical repo. The feature is fully opt-in and does not affect users who don't configure it.

## Alternatives considered

1. **sqlite-vec native extension**: Better query performance via ANN indexing, but adds a native dependency that complicates installation on some platforms. Rejected for MVP; can be adopted later as a performance optimization.

2. **LanceDB / Qdrant local**: Separate vector stores with their own file formats. Rejected because they break the single-SQLite-file story and add significant dependencies.

3. **Numpy for similarity**: Adds a large dependency (numpy) for a simple dot product. Rejected; pure Python `math` module handles 768-dim vectors across <10K chunks in sub-second time.

4. **AST-based context**: Parse code with tree-sitter and extract function/class boundaries for context. Complementary but orthogonal; could be added later. Embeddings provide broader semantic coverage without language-specific parsers.
