"""Abstract base class for detectors and a simple registry."""

from __future__ import annotations

import abc
import importlib.util
import logging
from importlib.metadata import entry_points
from pathlib import Path

from sentinel.models import CapabilityTier, DetectorContext, DetectorTier, Finding

logger = logging.getLogger(__name__)

# Common directories that all detectors should skip when walking the file tree.
# Detectors may extend this with domain-specific entries (e.g. "vendor" for Go).
COMMON_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".eggs",
    ".venv", "venv",
    "node_modules", ".next", ".turbo",
    "dist", "build", "out", "coverage",
    ".egg-info", ".sentinel",
})

# Module-level registry of detector classes
_REGISTRY: dict[str, type[Detector]] = {}


class Detector(abc.ABC):
    """Base class for all Sentinel detectors."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this detector."""

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Short human-readable description."""

    @property
    @abc.abstractmethod
    def tier(self) -> DetectorTier:
        """Classification tier: deterministic, heuristic, or llm-assisted."""

    @property
    @abc.abstractmethod
    def categories(self) -> list[str]:
        """Finding categories this detector can produce."""

    @property
    def capability_tier(self) -> CapabilityTier:
        """Model capability tier this detector requires.

        Defaults to NONE (no model needed). Override in LLM-assisted
        detectors to declare their minimum model requirement.
        """
        return CapabilityTier.NONE

    @property
    def enabled_by_default(self) -> bool:
        """Whether this detector runs when no explicit filter is configured.

        Defaults to True. Override to False for experimental or high-FP
        detectors that should only run when explicitly enabled.
        """
        return True

    @abc.abstractmethod
    def detect(self, context: DetectorContext) -> list[Finding]:
        """Run detection and return findings.

        Must not raise — return an empty list on internal errors
        and log the issue.
        """

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Auto-register concrete detector subclasses."""
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "__abstractmethods__", None):
            # Only register concrete classes (not intermediate ABCs)
            _register(cls)


def _register(cls: type[Detector]) -> None:
    """Register a detector class by instantiating it to get its name."""
    try:
        instance = cls()
        _REGISTRY[instance.name] = cls
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Detector %s failed to instantiate — registering by class name",
            cls.__name__,
        )
        _REGISTRY[cls.__name__] = cls


def get_registry() -> dict[str, type[Detector]]:
    """Return a copy of the detector registry."""
    return dict(_REGISTRY)


def get_all_detectors() -> list[Detector]:
    """Instantiate and return all registered detectors."""
    return [cls() for cls in _REGISTRY.values()]


def get_detector_info() -> list[dict[str, str]]:
    """Return metadata for all registered detectors.

    Ensures built-in and entry-point detectors are loaded first.
    Returns a list of dicts with keys: name, description, tier
    (capability tier value).
    """
    from sentinel.core.runner import _ensure_detectors_loaded
    _ensure_detectors_loaded()
    load_entrypoint_detectors()
    return [
        {"name": d.name, "description": d.description, "tier": d.capability_tier.value}
        for d in get_all_detectors()
    ]


def get_detector(name: str) -> Detector | None:
    """Get a detector instance by name, or None if not found."""
    cls = _REGISTRY.get(name)
    if cls is None:
        return None
    return cls()


def load_custom_detectors(detectors_dir: str | Path) -> list[str]:
    """Load custom detector classes from Python files in a directory.

    Each .py file is imported as a module. Any class extending Detector
    is auto-registered via __init_subclass__. Returns names of loaded detectors.
    """
    path = Path(detectors_dir)
    if not path.is_dir():
        logger.warning("Custom detectors directory not found: %s", path)
        return []

    loaded: list[str] = []
    before = set(_REGISTRY.keys())

    for py_file in sorted(path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"sentinel_custom_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                logger.warning("Could not load spec for %s", py_file)
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            logger.warning("Failed to load custom detector %s", py_file, exc_info=True)
            continue

    new_names = set(_REGISTRY.keys()) - before
    loaded.extend(sorted(new_names))
    if loaded:
        logger.info("Loaded custom detectors: %s", ", ".join(loaded))
    return loaded


def load_entrypoint_detectors() -> list[str]:
    """Discover and load third-party detectors via entry_points.

    Packages declare detectors in the ``sentinel.detectors`` entry-point
    group (see ADR-012). Each entry point module is imported, triggering
    ``__init_subclass__`` registration.

    Built-in detector names take priority — if an entry-point detector
    collides with a built-in name, the built-in class is restored after
    loading completes (TD-017 fix).

    Returns the names of newly registered detectors.
    """
    # Snapshot built-in classes BEFORE loading entry-points so we can
    # restore them if an entry-point overwrites a built-in name via
    # __init_subclass__ during ep.load().
    builtin_classes: dict[str, type[Detector]] = dict(_REGISTRY)
    before = set(_REGISTRY.keys())
    loaded: list[str] = []

    eps = entry_points(group="sentinel.detectors")
    for ep in eps:
        try:
            ep.load()  # triggers module import → __init_subclass__ registration
        except Exception:
            logger.warning(
                "Failed to load entry-point detector %r from %s",
                ep.name, ep.value, exc_info=True,
            )
            continue

    # Restore any built-in detectors that were overwritten during loading
    for name, cls in builtin_classes.items():
        if _REGISTRY.get(name) is not cls:
            logger.warning(
                "Entry-point detector overwrote built-in %r — restoring built-in",
                name,
            )
            _REGISTRY[name] = cls

    new_names = set(_REGISTRY.keys()) - before
    for name in sorted(new_names):
        loaded.append(name)

    if loaded:
        logger.info("Loaded entry-point detectors: %s", ", ".join(loaded))
    return loaded
