# Phase 9: Configurability, Plugins, and Finding Synthesis

> **Status**: Complete
> **Prerequisites**: Phase 8 capability-tier infrastructure complete
> **Goal**: Make Sentinel fully configurable for detector selection, model assignment, and third-party extension. Add finding cluster synthesis for smarter report output.

## Motivation

Strategic analysis (Session 29 conversation) identified three gaps:

1. **No detector selection**: Users cannot enable/disable specific detectors via config, CLI, or web UI. The `run_scan()` function accepts a `detectors` parameter but nothing exposes it.
2. **No plugin ecosystem**: Third-party detectors are limited to file-based `detectors_dir`. No `entry_points` discovery for pip-installable packages.
3. **Finding noise**: Self-scan produces 142 docs-drift findings. Many share root causes. Finding cluster synthesis can collapse these into actionable items.

User feedback: "The initial setup, where the user chooses detectors and the model they want to use, negates the risk of silently skipping detectors." This reframes detector configuration as a setup-time choice, not a runtime auto-skip.

## Acceptance Criteria

1. Users can enable/disable detectors via `sentinel.toml`, CLI flags, and web UI scan form
2. `model_capability` is settable via CLI (`--capability`)
3. Third-party detectors discoverable via `entry_points` (ADR-012)
4. Finding cluster synthesis produces root-cause grouped output for standard+ models
5. All new config paths are tested end-to-end (config → CLI → runner → output)

## Implementation Slices

### Slice 1: Detector Configurability (config + CLI + runner)
**Files**: `config.py`, `cli.py`, `core/runner.py`, tests
**What**:
- Add `enabled_detectors` and `disabled_detectors` list fields to `SentinelConfig`
- Add `--detectors` (comma-separated include list) and `--skip-detectors` (comma-separated exclude list) to CLI scan
- Add `--capability` to CLI scan for `model_capability`
- Wire filtering in runner before detector execution
- Validate detector names against registry

### Slice 2: Web UI Configurability
**Files**: `web/app.py`, `web/templates/scan.html`, tests
**What**:
- Add provider dropdown to scan form
- Add capability tier dropdown to scan form
- Add detector multi-select checkboxes to scan form
- Wire form values through to `run_scan()`

### Slice 3: Entry-Points Plugin Discovery (ADR-012)
**Files**: `detectors/base.py`, tests
**What**:
- Add `load_entrypoint_detectors()` using `importlib.metadata.entry_points`
- Called by runner after built-in detectors, before `detectors_dir`
- Handle import errors gracefully (log warning, continue)
- Name collision detection with warnings

### Slice 4: Finding Cluster Synthesis
**Files**: `core/synthesis.py` (new), `core/runner.py`, `core/report.py`, tests
**What**:
- Post-judge step: group findings by cluster, feed each cluster to LLM
- LLM identifies root cause, redundant findings, recommended action
- Requires `model_capability >= standard`
- Report displays synthesized clusters instead of raw finding lists
- Graceful degradation: skip synthesis when no model or basic tier

### Slice 5: Setup Flow Enhancement
**Files**: `cli.py` (init command), tests
**What**:
- Enhance `sentinel init` to guide detector selection
- List available detectors with descriptions and capability tiers
- Generate `sentinel.toml` with user's selected configuration
- Depends on OQ-011 resolution

## Dependencies

- Slice 1 has no dependencies (can start immediately)
- Slice 2 depends on Slice 1 (config fields must exist)
- Slice 3 is independent of Slices 1-2
- Slice 4 depends on Slice 1 (--capability CLI flag useful for testing)
- Slice 5 depends on Slices 1 + 3 (needs to list all detectors including plugins)

## Open Questions

- OQ-011: Setup flow design (how interactive should `sentinel init` be?)
- OQ-012: Per-detector model configuration (different models for different detectors?)
