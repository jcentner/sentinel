# VISION-REVISION-004: Web UI Expansion — Full CLI Parity and Design System

> **Created**: 2026-04-06
> **Applies to**: VISION-LOCK.md §"MVP Scope", VISION-REVISION-002.md §"Scope"

## Change

VISION-REVISION-002 defined the web UI as a minimal review layer: run history, findings by severity, inline approve/suppress, scan trigger, and a scheduling feature. This revision documents the actual shipped state of the web UI after Session 12, which significantly exceeds VR-002's scope while deliberately omitting the built-in scheduling feature.

The web UI now provides **full CLI workflow parity** — everything a user would realistically do in their daily triage routine can be done from the browser without touching the terminal.

### What was added beyond VR-002

| Feature | Description |
|---------|-------------|
| **Dark-mode design system** | "Night Watch" theme — dark-first design with warm amber accent on navy-black. Full light mode alternative via toggle button. CSS custom properties for complete theming. |
| **Typography system** | Bricolage Grotesque (display/body, variable optical sizing) + JetBrains Mono (code/evidence). Loaded from Google Fonts. |
| **GitHub Issues page** (`/github`) | Dashboard showing GitHub configuration status, list of approved findings, batch "Create Issues" and "Dry Run" buttons. Full parity with `sentinel create-issues` CLI command. |
| **Configurable Scan form** (`/scan`) | Form-based scan initiation with repo path input, LLM model override, embedding model, skip-judge toggle, incremental toggle. Replaces the simple "Scan Now" button from VR-002. |
| **Suppress with reason** | Inline reason text input on finding detail page. Parity with `sentinel suppress --reason`. |
| **Severity stat cards** | Run detail page shows 4 stat cards (critical/high/medium/low counts) for at-a-glance severity distribution. |
| **Theme persistence** | Dark/light mode preference stored in `localStorage`, applied via inline script before render to prevent flash. |
| **Toast notifications** | Auto-dismissing notification system for htmx action feedback (approve/suppress success). |
| **Repo indicator** | Header shows current repo basename for context. |
| **Active nav highlighting** | Current page highlighted in navigation links. |
| **Status-aware actions** | Finding detail page shows contextual actions based on current status (different messages for new, approved, suppressed, resolved). |
| **Recurrence info** | Finding detail shows occurrence count and first-seen date when available. |

### What VR-002 specified but was NOT implemented

| Feature | Status | Rationale |
|---------|--------|-----------|
| **Built-in scheduling** (cron expression in `sentinel.toml`) | **Not implemented** | Architecture overview and ADR decisions consistently say Sentinel should not include a built-in scheduler. System cron/systemd timers are better suited (more reliable, configurable, observable). This was a deliberate architectural choice, not an oversight. Tracked as TD-009. |
| **Root-cause finding grouping** in UI | **Partially implemented** | The report layer has directory-based clustering. The web UI groups by severity but does not yet cluster by root cause within severity groups. |

### Complete route inventory (9 routes)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Redirect to latest run, or empty state |
| GET | `/runs` | Run history table with severity badges |
| GET | `/runs/{id}` | Run detail: stat cards, filters, findings by severity |
| GET | `/findings/{id}` | Finding detail: metadata, description, evidence, actions |
| POST | `/findings/{id}/action` | Approve or suppress (htmx-friendly) |
| GET/POST | `/scan` | Scan configuration form / trigger scan |
| GET | `/github` | GitHub Issues dashboard |
| POST | `/github/create-issues` | Create issues from approved findings |
| static | `/static` | CSS, JS, htmx |

## Rationale

### CLI parity serves the morning review workflow

The 2-minute morning review constraint (VISION-LOCK success criterion #2) is best served when a user can complete a full triage cycle — review findings, approve for issues, create GitHub issues — without switching between browser and terminal. The GitHub Issues page and configurable scan form close the last gaps that required CLI interaction.

### A design system prevents "AI slop" aesthetics

The Sentinel tool runs every morning — it needs to feel like a tool the user trusts and wants to use. A distinctive visual identity (Night Watch dark theme, purposeful typography, amber accent language) communicates intentionality and quality. Generic UI templates would undermine the project's credibility positioning.

### Scheduling belongs to the OS, not the application

VR-002's scheduling feature assumed the web server should manage cron-like scheduling internally. After implementation experience, this was rejected because:
- System schedulers (cron, systemd timers) are more reliable, observable, and configurable
- A built-in scheduler adds complexity, state management, and failure modes
- The architecture docs consistently describe Sentinel as a single-run tool triggered externally
- Users who `sentinel serve` for the web UI may not want it to also run scans

This is tracked as TD-009 with a clear rationale, not silently dropped.

## Evidence

- Session 12 implementation: all code reviewed and tested
- 436 tests passing (38 web tests), mypy strict clean, ruff clean
- Browser-tested in both dark and light modes across all pages
- htmx actions verified: approve, suppress, scan, theme toggle

## Impact on Existing Artifacts

| Artifact | Required Update |
|----------|----------------|
| Architecture overview §10 (Web UI) | Update with full route list, design system, new pages |
| README §Web UI | Update feature bullets |
| OQ-002 resolution | Update to reflect web UI as shipped |
| Glossary | Add: serve mode, Night Watch, theme toggle |
| Tech Debt | Add TD-009 for VR-002 scheduling gap |

## Source Basis

| Claim | Source |
|-------|--------|
| Web UI needs full CLI parity for daily workflow | VISION-LOCK §Success Criteria #2 (2-minute review) |
| Scheduling should be external | Architecture overview §Trigger Modes, Session 11 checkpoint |
| Night Watch theme design direction | Frontend-design skill (Anthropic), Impeccable style patterns |
| VR-002 original scope | VISION-REVISION-002.md §Scope |
