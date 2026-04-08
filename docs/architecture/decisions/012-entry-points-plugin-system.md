# ADR-012: Entry-Points Plugin System for Third-Party Detectors

**Status**: Accepted
**Date**: 2026-04-08
**Deciders**: Jacob Centner

## Context

Sentinel supports custom detectors via `detectors_dir` config — users drop `.py` files in a directory and `load_custom_detectors()` imports them. The `__init_subclass__` hook on `Detector` auto-registers any concrete subclass on import.

This works for local development but has limitations:

1. **No package-based distribution**: A third party cannot `pip install sentinel-detector-xyz` and have it auto-discovered. They must manually copy files into a `detectors_dir`.
2. **No dependency management**: File-based detectors can't declare their own dependencies. Entry-points-based detectors ship as proper Python packages with `pyproject.toml`.
3. **No versioning**: File-based detectors have no version metadata.

The existing `detectors_dir` mechanism is simple and should be preserved for quick local development. But for ecosystem growth, a package-based discovery mechanism is needed.

## Decision

Adopt Python `entry_points` (specifically the `sentinel.detectors` group) as the primary third-party detector discovery mechanism, alongside the existing `detectors_dir` for local development.

### Discovery order

1. **Built-in detectors**: Always loaded first (the 14 shipped detectors).
2. **Entry-points detectors**: Discovered via `importlib.metadata.entry_points(group="sentinel.detectors")`. Each entry point's `load()` triggers the module import, and `__init_subclass__` handles registration.
3. **Local file detectors**: Loaded from `detectors_dir` config (existing behavior, unchanged).

### Third-party package contract

A third-party detector package declares an entry point in its `pyproject.toml`:

```toml
[project.entry-points."sentinel.detectors"]
my_detector = "my_package.detector_module"
```

The module must contain one or more concrete `Detector` subclasses. No other registration is needed — `__init_subclass__` handles it.

### Detector metadata requirements

Third-party detectors must declare:
- `name`: Unique identifier (collisions with built-in names are rejected with a warning)
- `description`: Human-readable description
- `tier`: DetectorTier classification
- `categories`: Finding categories produced
- `capability_tier`: Minimum model capability needed (defaults to NONE)

### Conflict resolution

If an entry-points detector has the same `name` as a built-in detector, the built-in wins and a warning is logged. If two entry-points detectors collide, the first discovered wins with a warning.

## Consequences

### Positive
- Third parties can distribute detectors as pip-installable packages
- Version management and dependency tracking via standard Python packaging
- Detector ecosystem can grow independently of Sentinel core releases
- `detectors_dir` remains for quick local prototyping

### Negative
- Slightly more complex discovery code in `base.py`
- Must handle import errors gracefully (a broken third-party detector must not crash the pipeline)
- Entry-points discovery adds a small startup cost (negligible in practice)

### Risks
- Malicious third-party detectors could execute arbitrary code on import. This is inherent to Python's plugin model and is the user's responsibility (same as `pip install` anything).
