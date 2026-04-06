# System Architecture Overview

> **Status**: Active — reflects implementation as of 2026-04-06.

## High-level data flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         Sentinel Run                             │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐     │
│  │  Detectors   │───▶│  Fingerprint │───▶│  Deduplicator    │     │
│  │ (Tiers 1-3)  │   │  Assignment  │   │  (suppress +     │     │
│  │              │   │  (SHA-256)   │   │   cross-run)     │     │
│  └─────────────┘    └─────────────┘    └──────────────────┘     │
│                                               │                  │
│                                               ▼                  │
│  ┌──────────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │  Context Gatherer │◀──│  Deduped      │───▶│  LLM Judge    │   │
│  │  (heuristic +     │   │  Findings     │   │  (Ollama)     │   │
│  │   embeddings)     │   └──────────────┘    └──────────────┘   │
│  └──────────────────┘                               │            │
│                                                     ▼            │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐     │
│  │  State Store │◀──│  Persistence  │◀──│  Judged Findings │     │
│  │  (SQLite v7) │   │  Tracker     │   │                  │     │
│  └─────────────┘    └─────────────┘    └──────────────────┘     │
│                           │                                      │
│                           ▼                                      │
│                    ┌─────────────┐    ┌──────────────┐           │
│                    │  Morning     │───▶│  Human        │           │
│                    │  Report      │    │  Approval     │           │
│                    │ (+ clustering)│    └──────────────┘           │
│                    └─────────────┘           │                   │
│                                              ▼                   │
│                                       ┌──────────────┐           │
│                                       │  GitHub       │           │
│                                       │  Issue Creator│           │
│                                       └──────────────┘           │
└──────────────────────────────────────────────────────────────────┘
```

**Pipeline order:** Detectors → Fingerprint → Dedup → Context → Judge → Persistence → Store → Report. Dedup runs *before* context gathering and judging to avoid wasting effort on suppressed or duplicate findings.

## Component responsibilities

### 1. Detectors

Detectors produce raw candidate findings. They come in three tiers:

**Tier 1 — Deterministic**: Lint output (ruff for Python, ESLint/Biome for JS/TS), TODO/FIXME scanning, dependency audit (pip-audit). Cheap, reliable, no model needed.

**Tier 2 — Heuristic**: Git-history hotspots (commit frequency analysis), cyclomatic complexity / function length analysis. Also model-free.

**Tier 3 — LLM-assisted**: Docs-drift doc-code comparison via Ollama. The model evaluates whether documentation accurately describes the code, not the primary signal source.

The architecture is **mostly Tier 1 + 2, with the LLM as the judgment/summarization layer**, not the primary signal source.

Every detector produces a `Finding` conforming to the [Detector Interface](detector-interface.md).

**Implemented detectors**: `todo-scanner` (T1), `lint-runner` (T1), `eslint-runner` (T1), `go-linter` (T1), `rust-clippy` (T1), `dep-audit` (T1), `docs-drift` (T1+T3), `git-hotspots` (T2), `complexity` (T2).

### 2. Fingerprint Assignment

Each finding receives a content-based fingerprint (SHA-256 of `detector:category:file_path:normalized_content`, truncated to 16 hex chars). Normalization is detector-specific to ensure stability across trivial changes like whitespace or line-number shifts.

### 3. Deduplicator

Compares fingerprints against the state store to:
- Skip previously suppressed findings
- Skip duplicates within the same run
- Mark recurring findings (found in prior runs) for higher visibility

### 4. Context Gatherer

For each candidate finding, retrieves supporting context using two strategies:

**Heuristic context** (always active):
- Surrounding code lines (±5 lines around the affected location)
- Related test files (convention-based matching: `test_<module>.py`)
- Recent git log for the affected file

**Embedding-based semantic context** (opt-in via `embed_model` config):
- Repo files are chunked (50-line windows with 10-line overlap) and embedded via Ollama `/api/embed`
- Embeddings stored as float32 BLOBs in the SQLite `chunks` table
- For each finding, the title + description are embedded and compared against all chunks via cosine similarity
- Top-5 most relevant chunks (above similarity threshold 0.3) added as additional evidence
- Incremental indexing: only re-embeds files whose content has changed
- Falls back gracefully to heuristic-only if embeddings are unavailable

See ADR-009 for full architecture decisions.

### 5. LLM Judge

A small local model (via Ollama) that receives each finding + its gathered context and answers:
- Is this likely real?
- What evidence supports it?
- How severe is it?

This is a structured judgment task, not open-ended generation. The model doesn't invent findings — it evaluates candidates produced by deterministic/heuristic detectors. The judge is optional and can be skipped with `--skip-judge`.

### 6. Persistence Tracker

Updates per-fingerprint occurrence counts. Findings seen across multiple runs get `occurrence_count` and `recurring` annotations, enabling the report to show recurrence badges (♻️ ×N) and new-vs-recurring breakdowns.

### 7. State Store (SQLite)

Persistent state across runs. Tracks:
- Previous findings (fingerprinted for dedup)
- Suppression flags (user-marked false positives)
- Run history (when, what scope, how many findings, commit SHA)
- Finding lifecycle (new → confirmed → approved → suppressed → resolved)
- Finding persistence (occurrence counts across runs)
- LLM interaction log (prompts, responses, tokens, timing, verdicts for every LLM call)

Schema version is tracked with an ordered migration framework. Current schema: v7.

This is a Phase 1 design decision, not a later addition. Deduplication is a trust feature.

### 8. Morning Report

Primary output. Markdown formatted, designed to be scannable in under 2 minutes:
- One line per finding with severity, confidence, category
- Findings grouped by severity → category
- Related findings clustered by directory (3+ findings collapse into `<details>` blocks)
- Expandable evidence sections
- Judge summary and verdict badges (♻️ recurring, ⚠️ FP?)
- Clear approve/suppress actions per finding with fingerprint IDs
- Summary statistics (severity counts, new vs recurring, per-detector breakdown)
- LOW findings truncated at 20 to prevent report bloat

### 9. GitHub Issue Creator

Takes approved findings and creates GitHub issues. Only runs after explicit human approval via `sentinel create-issues`. Deduplicates against existing open issues using fingerprint markers in issue bodies. Supports dry-run mode.

### 10. Web UI

Optional browser-based review and management interface (`sentinel serve <repo>`). Starlette + Jinja2 with htmx for progressive enhancement. "Night Watch" design system — dark-first with warm amber accent, Bricolage Grotesque + JetBrains Mono typography, with a light mode toggle. No JavaScript build step.

**Pages and routes:**

| Route | Purpose |
|-------|--------|
| `/` | Redirect to latest run, or empty state |
| `/runs` | Run history table with scope badges |
| `/runs/{id}` | Run detail: severity stat cards, filters, findings by severity group |
| `/findings/{id}` | Finding detail: metadata, description, evidence, approve/suppress with reason |
| `/scan` | Configurable scan form: repo path, model override, skip-judge, incremental |
| `/github` | GitHub Issues dashboard: config status, approved findings, create/dry-run |
| `/settings` | Read-only configuration viewer: sentinel.toml status, GitHub env vars |
| `/eval` | Evaluation form + results: run detectors against ground-truth TOML |
| `/eval/history` | Evaluation history: precision/recall trends over time |
| `/runs/{id}/compare/{base_id}` | Run comparison: new, resolved, and persistent findings between two runs |

**Key capabilities:**
- Full CLI workflow parity — daily triage (review, approve, suppress, create issues) without the terminal
- Dark/light theme toggle with `localStorage` persistence, no-flash inline script
- htmx inline actions (approve/suppress update status badge without page reload)
- Severity stat cards for at-a-glance distribution on run detail
- GitHub issue creation with dry-run from the browser
- Scan form with model/embedding/judge/incremental options
- Localhost-only by default, no authentication required
- Optional dependency group (`pip install sentinel[web]`)
- Reads the same SQLite database — CLI and web share a single source of truth

## What runs where

| Component | Runs on | Resource profile |
|-----------|---------|-----------------|
| Detectors | CPU | Lightweight — linters, grep, subprocess |
| Context Gatherer | CPU + GPU (optional) | File reads, git log commands, Ollama embed API (when embeddings enabled) |
| LLM Judge | GPU (8 GB VRAM) | Qwen3.5 4B Q4_K_M via Ollama (~2.8 GB) |
| State Store | Disk | SQLite, negligible |
| Report | CPU | Markdown generation |

Embeddings are implemented via Ollama's `/api/embed` endpoint (ADR-009). Reranker models are not yet implemented.

## Trigger modes

- **Manual**: On-demand CLI invocation (`sentinel scan <repo>`) — the primary trigger mode.
- **Web UI**: Configurable scan form in `sentinel serve` web interface — supports repo path override, model selection, skip-judge, and incremental mode.
- **Cron / systemd timer**: Users can schedule overnight runs using their system's cron or systemd timer. See the README for setup instructions. Sentinel itself does not include a built-in scheduler.
- **Git hook**: On last push of the day or on specific events (not implemented — potential future addition).
- **Watch**: File-system watcher for continuous development (not implemented — future).

## Scope per run

- **Full**: Entire repository (default). Runs all detectors on all files.
- **Incremental**: Changed files since last completed run. Enabled via `--incremental` CLI flag.
- **Targeted**: Specific paths or detector categories (available in runner API via `target_paths` parameter; CLI `--target` flag available).
