# VISION-REVISION-003: Embedding-Based Context Delivered in Phase 1

> **Created**: 2026-04-05
> **Applies to**: VISION-LOCK.md §"MVP Scope" → "Not in MVP scope" table

## Change

The vision lock listed "Embeddings-based context" under "Not in MVP scope" as "Phase 1 stretch or Phase 2". This feature was implemented in Session 9 as part of Phase 1.

## What changed

The embedding-based context gatherer is now shipped:
- Opt-in via `embed_model` config or `--embed-model` CLI flag
- Uses Ollama `/api/embed` for chunk embeddings
- Stores vectors as float32 BLOBs in the existing SQLite database
- Incremental re-indexing via content hashing
- Graceful fallback to file-proximity heuristics when unavailable

## Why

The context gatherer was identified as the single highest-leverage quality improvement remaining. The LLM judge's accuracy is directly limited by the context it receives. Moving from ±5 lines of surrounding code to semantically similar chunks across the repo meaningfully improves judgment quality.

## Evidence

- ADR-009 documents the full architecture decision
- OQ-004 resolved (embedding model and vector store choice)
- TD-001 resolved (context gatherer upgraded)
- 35 tests covering store, indexer, context integration, and failure modes

## Downstream updates required

- Architecture overview updated (Session 9)
- Glossary updated with embedding-related terms (Session 9)
- README updated with `sentinel index` and `--embed-model` usage (Session 9)
- No changes to core pipeline semantics — existing behavior is unchanged when embeddings are not configured
