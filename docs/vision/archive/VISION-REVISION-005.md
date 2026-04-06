# VISION-REVISION-005: Web UI — Bulk Triage, Settings, and Evaluation Pages

> **Created**: 2026-04-06
> **Applies to**: VISION-REVISION-004.md §"Complete route inventory"

## Change

VISION-REVISION-004 documented 9 routes as the complete web UI. Session 13 added three new capabilities that extend the web UI beyond VR-004:

### What was added

| Feature | Route | Description |
|---------|-------|-------------|
| **Bulk approve/suppress** | `POST /runs/{id}/bulk-action` | Select multiple findings via checkboxes, batch approve or suppress from a sticky action bar. Per-severity "select all" toggles. htmx toast + page reload. |
| **Settings page** | `GET /settings` | Read-only view of active SentinelConfig fields, sentinel.toml detection status, and GitHub env var status. |
| **Evaluation page** | `GET/POST /eval` | Form-based eval: specify repo + ground-truth file, runs detectors with `skip_judge=True`, displays precision/recall as stat cards with pass/fail thresholds, lists missing findings and unexpected FPs. |

### Complete route inventory (12 routes)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Redirect to latest run, or empty state |
| GET | `/runs` | Run history table with severity badges |
| GET | `/runs/{id}` | Run detail: stat cards, filters, bulk checkboxes, findings by severity |
| POST | `/runs/{id}/bulk-action` | Bulk approve/suppress selected findings |
| GET | `/findings/{id}` | Finding detail: metadata, description, evidence, actions |
| POST | `/findings/{id}/action` | Approve or suppress single finding (htmx-friendly) |
| GET/POST | `/scan` | Scan configuration form / trigger scan |
| GET | `/github` | GitHub Issues dashboard |
| POST | `/github/create-issues` | Create issues from approved findings |
| GET | `/settings` | Configuration viewer |
| GET/POST | `/eval` | Evaluation form / results |
| static | `/static` | CSS, JS, htmx |

## Rationale

### Bulk triage completes the morning review workflow

The 2-minute scannability constraint (VISION-LOCK success criterion #2) is undermined if a user must click into each finding individually to approve or suppress it. Bulk actions allow reviewing a 20+ finding scan and acting on entire severity groups in seconds.

### Settings visibility reduces debugging friction

Users encountering unexpected behavior (wrong model, missing embeddings) need a way to verify current configuration without reading TOML files. A read-only settings dashboard serves this without introducing config mutation complexity.

### Eval page supports quality measurement

ADR-008 defined eval metrics but measuring them required the CLI. An eval page lets users verify detector quality from the browser, supporting the project's credibility mandate.

## Evidence

- 20 new tests (TestBulkActions: 10, TestSettingsPage: 5, TestEvalPage: 5)
- 456 total tests passing
- README updated with new feature descriptions

## Downstream updates required

- README updated (Session 13) ✓
- CURRENT-STATE updated (Session 13) ✓
- No architecture changes — all new routes use existing store functions
