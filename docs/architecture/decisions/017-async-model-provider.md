# ADR-017: Async Model Provider with Backward-Compatible Concurrency

**Status**: Accepted
**Date**: 2026-04-13
**Supersedes**: Aspect of TD-002 (sync detector interface), TD-016 (serial LLM bottleneck)

## Context

The judge processes findings sequentially — each `provider.generate()` call blocks until complete (~4s for cloud, longer for local). With 100 findings, the judge alone takes 7+ minutes (TD-016). Synthesis adds more serial calls. This is the only medium-severity tech debt item.

The `ModelProvider` protocol (ADR-010) defines synchronous methods. Third-party detectors via entry-points (ADR-012) implement this protocol. Any async migration must not break existing providers.

## Decision

### Duck-typed async methods (no Protocol change)

Rather than modifying the `ModelProvider` Protocol or creating a parallel `AsyncModelProvider` Protocol, we use duck-typed optional async methods:

1. Built-in providers (Ollama, OpenAI-compat, Azure) add `agenerate()` and `aembed()` methods using `httpx.AsyncClient`.
2. The `ModelProvider` Protocol is **not modified** — existing third-party providers continue to work.
3. A helper function `agenerate()` in `provider.py` checks for a native `agenerate` method via `hasattr()`; if absent, wraps `generate()` in `asyncio.to_thread()`.
4. Judge and synthesis convert to async internals (`ajudge_findings`, `asynthesize_clusters`) with bounded concurrency via `asyncio.Semaphore`.
5. `run_scan()` remains synchronous at its boundary — it calls `asyncio.run()` for the async judge/synthesis sections. The web app (already async via Starlette) can call the async functions directly in the future.

### Concurrency bounds

- Judge: `max_concurrent_judges = 8` (configurable). Cloud APIs handle this easily; local Ollama benefits less but doesn't break.
- Synthesis: `max_concurrent_synthesis = 4` (fewer, larger prompts).
- SQLite logging: Thread-safe via `check_same_thread=False`, but writes are serialized by SQLite's single-writer lock — this is fine for logging.

## Consequences

- **Positive**: 100-finding judge pass drops from ~7 min to ~1 min with cloud provider (8 concurrent calls × 4s each ≈ 50s).
- **Positive**: Zero breaking changes to `ModelProvider` protocol or entry-point plugins.
- **Positive**: Providers without `agenerate()` automatically get thread-pool concurrency (still faster than serial).
- **Negative**: Two code paths (sync + async) must stay consistent.
- **Negative**: `asyncio.run()` inside `run_scan()` means the scan can't be nested inside another async context without refactoring (acceptable trade-off for now).

## Alternatives Considered

1. **Separate `AsyncModelProvider` Protocol**: Clean but forces all consumers to handle two types. Over-engineered for current need.
2. **Thread pool only (no native async)**: Simpler but wastes threads on I/O-bound HTTP calls. httpx has native async support — use it.
3. **Make `run_scan()` fully async**: Eventually desirable but huge migration surface. Incremental is better.
