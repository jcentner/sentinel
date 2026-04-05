# VISION-REVISION-002: Web UI, Scheduling, and Usability Layer

> **Created**: 2026-04-05
> **Applies to**: VISION-LOCK.md §"MVP Scope", §"Success Criteria", §"Product Constraints"

## Change

The locked vision defines the primary output as a markdown file and the interaction surface as CLI commands. This revision adds:

1. **`sentinel serve`** — a local web server providing a browser-based review and management interface.
2. **Built-in scheduling** — `sentinel serve` can run scans on a configurable schedule, making "overnight" runs automatic rather than manually triggered.
3. **Finding grouping** — findings from a common root cause (e.g., a renamed directory producing many stale links) are grouped in both the report and the UI.

The CLI remains the primary scriptable interface. The web UI is a layer on top, not a replacement. All state flows through the existing SQLite store.

## Rationale

### The 2-minute morning review constraint is not met by the current UX

The VISION-LOCK defines success criterion #2 as: "The morning report is scannable in under 2 minutes." The current workflow requires reading a markdown file, then copy-pasting finding IDs into a terminal for approve/suppress actions. The review itself may meet 2 minutes, but the full triage loop — review, act, create issues — is significantly slower and more friction-heavy than it needs to be.

A browser-based view with inline approve/suppress buttons and expandable evidence directly serves this constraint better than markdown + CLI.

### "Overnight" requires scheduling

The strategy document describes Sentinel as working "in the background" and producing results "in the morning." But no scheduling mechanism exists — the user must remember to manually run scans. This contradicts the core concept of an overnight monitor. Adding scheduling to `sentinel serve` makes the system match its own description.

### Usability is a trust feature

The project's value depends on adoption into a daily routine. A tool that works correctly but is tedious to use will be abandoned. Precision without usability is wasted precision. The competitive landscape analysis notes that Sentinel's positioning gap is "persistent, scheduled observation with human-gated issue creation" — scheduled and human-gated both require better interaction than a CLI.

### Finding grouping is noise reduction

Real-world validation (396 findings on a TypeScript repo) showed that many findings share a root cause. Without grouping, the UI (or report) presents N repetitive entries that could be one actionable item. This is a direct false-positive-rate concern — repeated findings from the same cause inflate perceived noise even when each individual finding is technically correct.

## Scope

### In scope

| Component | Description |
|-----------|-------------|
| `sentinel serve` command | Starts a local HTTP server on `localhost`. Serves the web UI and optionally runs scheduled scans. |
| Morning report view | Default page. Findings grouped by severity, expandable evidence, inline approve/suppress/dismiss actions. Filter by detector, severity, status. |
| Run history view | Past scan runs with summary stats. |
| Scan trigger | Manual "run scan now" button in the UI. |
| Scheduling | Configurable scan schedule (cron expression or interval) via `sentinel.toml`. Runs in the background while the server is active. |
| Finding grouping | Cluster findings that share a root cause. Display as collapsible groups in the UI and in the markdown report. |

### Constraints

| Constraint | Rationale |
|------------|-----------|
| Localhost only — no network binding | Local-first execution (ADR-001). Single-user tool. No auth needed. |
| No JavaScript build step | Python project. Frontend must be maintainable without Node/npm. Use server-rendered templates with progressive enhancement (htmx or similar). |
| No new runtime dependencies beyond Python ecosystem | FastAPI/Starlette + Jinja2 are pure Python. No separate process, no Docker, no second language runtime. |
| CLI remains fully functional | The web UI is additive. Every action available in the UI must also be available via CLI. |
| `pip install sentinel` still works | The web UI ships with the package. No post-install setup. `sentinel serve` just works. |
| SQLite remains the single source of truth | The web UI reads from and writes to the same database the CLI uses. No separate state. |

### Not in scope (explicit boundaries)

- User accounts, authentication, or multi-user access
- Cloud hosting, Docker packaging, or remote deployment
- Slack/Discord/email notifications
- Real-time WebSocket updates or live tailing
- Mobile-responsive design (desktop browser on localhost is the use case)

## Impact on Success Criteria

The existing success criteria remain unchanged. This revision adds:

- **8. A developer can start `sentinel serve`, open a browser, and review/act on findings without using the CLI.** The web UI provides the same approve/suppress/create-issues workflow as the CLI, with lower friction.
- **9. Scheduled scans produce results automatically.** When `sentinel serve` is running with a configured schedule, scans run without manual triggering.

## Impact on Existing Artifacts

| Artifact | Required Update |
|----------|-----------------|
| `docs/architecture/overview.md` | Add web server component to architecture diagram. Document `sentinel serve` as a trigger mode. |
| `docs/reference/open-questions.md` | Resolve OQ-002 (report delivery mechanism) — answered by web UI + scheduled serve. |
| `docs/reference/glossary.md` | Add terms: `serve mode`, `finding group`, `root cause clustering`. |
| `pyproject.toml` | Add runtime dependencies (FastAPI/Starlette, Jinja2, uvicorn). |
| `roadmap/CURRENT-STATE.md` | Update with new scope items. |
| `README.md` | Document `sentinel serve` command and web UI. |

## Source Basis

| Claim | Source |
|-------|--------|
| 2-minute scannability is a product constraint | VISION-LOCK §"Product Constraints"; strategy.md §"Primary output" |
| Overnight/background operation is the core concept | strategy.md §"Core concept", §"Why this exists" |
| Human approval gate for all external actions | VISION-LOCK §"Product Constraints"; strategy.md §"Primary output" |
| Local-first, no cloud | ADR-001; VISION-LOCK §"Technical Constraints" |
| Precision over breadth, noise reduction matters | positioning.md §"The one trap to avoid"; critical-review.md §"Honest concerns" |
| Finding grouping needed based on real-world validation | Session 6 notes (396 findings, many from shared root causes) |
| Scheduling as a missing capability | strategy.md describes "overnight" but no implementation exists; VISION-LOCK §"Core Concept" says "runs on a schedule" |
| OQ-002 identifies report delivery as an open question | open-questions.md §OQ-002 |
