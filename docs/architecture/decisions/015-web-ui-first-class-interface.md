# ADR-015: Web UI as first-class interaction surface

**Status**: Accepted
**Date**: 2026-04-11
**Deciders**: Project founder

## Context

The web UI was built as a triage dashboard: view findings, approve/suppress, create GitHub issues. Configuration management lives exclusively in the CLI (`sentinel init`) and manual `sentinel.toml` editing.

User testing revealed a design problem. The web UI is the natural discovery surface — humans testing Sentinel open the browser first, try to understand what the tool does, and immediately ask "why can't I do anything in here?" The settings page displays config but can't edit it. The GitHub page shows env var status but can't change it. The compatibility page shows model-detector quality ratings but can't configure model selection. Seven tech debt items (TD-046 through TD-052) are symptoms of this single root cause.

The vision lock specifies "Dual interface: feature parity between CLI and web UI" but the architecture doesn't support it. The CLI has 13 commands; the web UI can do 3 things (scan, triage, create issues).

## Decision

**The web UI is a first-class interaction surface, on par with the CLI.** Not a read-only dashboard.

### Architectural changes

1. **Route modules** — Split the monolithic `app.py` (~870 lines, 17 routes) into domain-specific route modules under `web/routes/`. Shared helpers (templates, DB access) move to `web/shared.py`.

2. **Config write layer** — Add `save_config(repo_path, config)` to `config.py`. Writes `sentinel.toml` with proper TOML formatting. No new dependency — manual TOML serialization for the simple schema we have.

3. **Settings page** becomes read-write. Users can modify config fields and save to `sentinel.toml`. Equivalent to `sentinel init` + manual editing.

4. **Detectors page** (renamed from Compatibility) becomes the primary detector/model configuration surface. Combines: quality ratings matrix, detector toggles (enable/disable), per-detector model selection, and the ability to persist these choices. This is the page where "what should I use?" meets "let me configure it."

5. **Feature parity principle** refined: every CLI-accessible action should have a web UI equivalent. The interfaces are complementary — CLI for automation and scripting, web for visual discovery and configuration.

### Config write implementation

Manual TOML serialization (no `tomli_w` dependency) that:
- Writes only non-default values to keep the file clean
- Preserves the `[sentinel]` table structure
- Handles nested `[sentinel.detector_providers.X]` tables
- Respects file atomicity (write to temp file, then rename)

### Route module structure

```
web/
├── __init__.py
├── app.py          ← create_app() factory only
├── csrf.py         ← CSRF middleware (unchanged)
├── shared.py       ← templates, _get_conn, _open_db
├── routes/
│   ├── __init__.py
│   ├── findings.py ← finding detail, actions, annotations, bulk
│   ├── runs.py     ← runs list, run detail, comparison
│   ├── scan.py     ← scan form + trigger
│   ├── settings.py ← settings display + edit (NEW: write)
│   ├── detectors.py← detectors page (renamed from compatibility + config)
│   ├── eval.py     ← eval form + trigger + history
│   └── github.py   ← GitHub dashboard + issue creation
├── static/
└── templates/
```

## Consequences

### Positive
- Web UI becomes the onboarding and discovery surface — new users can understand and configure Sentinel without touching the CLI
- Feature parity resolves 7 tech debt items (TD-046 through TD-052)
- Route modules make the codebase navigable — ~100 lines per module instead of ~870 in one file
- Config write layer is reusable by both CLI and web

### Negative
- More files to maintain (8 route modules + shared.py vs 1 app.py)
- Config write must handle concurrent access and file permission errors
- Web-based config editing introduces a new class of security considerations (CSRF is already handled; path traversal for repo_path needs continued attention)

### Neutral
- Existing tests interact through the HTTP client and `create_app()` — route module split doesn't affect test structure
- Template files are unchanged; only Python route organization changes

## Alternatives considered

### Option A: Keep web UI as read-only dashboard
The web UI stays a triage tool. Configuration happens exclusively via CLI and text editor. Resolves display TDs (TD-048 through TD-051) but closes TD-046 and TD-047 as won't-fix.

**Rejected**: Doesn't address the discovery problem. Users trying the tool in the browser hit a wall immediately.

### Option C: Surgical middle ground — only detector/model config
Build only the detector configuration page (quality ratings + toggles + model selection). Everything else stays CLI-only.

**Considered but too narrow**: The settings page already shows the data — making it read-write is incremental work once the config write layer exists. Stopping at one page creates an inconsistent experience ("I can edit this here but not that").
