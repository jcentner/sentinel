# ADR-007: Python as implementation language

**Status**: Accepted
**Date**: 2026-04-03
**Deciders**: Human (project owner)

## Context

OQ-001 asked whether Sentinel should be written in Python or TypeScript. Both are viable. Sentinel needs to interact with CLI tools, parse ASTs (tree-sitter), manage SQLite, call the Ollama HTTP API, and generate markdown reports.

The target repos being scanned are primarily TypeScript and some Python. However, Sentinel itself is a standalone tool, not a library consumed by those repos.

## Decision

Sentinel will be implemented in **Python**.

## Consequences

**Positive:**
- Richer ML/NLP ecosystem for embeddings, reranking, and text processing
- Mature tree-sitter bindings (`tree-sitter` Python package)
- Native SQLite support (`sqlite3` stdlib module)
- Strong CLI tooling ecosystem (`click`, `typer`, `argparse`)
- Simpler dependency story for the retrieval/embedding stack
- Aligns with the "current thinking" already documented in OQ-001

**Negative:**
- Does not align with the primary target repos' language (TypeScript)
- Type checking requires additional tooling (mypy/pyright) vs TypeScript's built-in types
- Packaging and distribution is less straightforward than a single Node binary

**Neutral:**
- Ollama HTTP API is language-agnostic (REST), no advantage either way
- Markdown generation is trivial in both languages

## Alternatives considered

**TypeScript**: Would align with target repos and provide built-in type safety. Rejected because the ML-adjacent ecosystem (embeddings, reranking, tree-sitter) has significantly more friction in Node.js, and Sentinel is a standalone tool, not a library for the target repos.
