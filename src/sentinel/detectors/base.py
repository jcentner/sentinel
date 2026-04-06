"""Abstract base class for detectors and a simple registry."""

from __future__ import annotations

import abc
import importlib.util
import logging
from pathlib import Path

from sentinel.models import DetectorContext, DetectorTier, Finding

logger = logging.getLogger(__name__)

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
