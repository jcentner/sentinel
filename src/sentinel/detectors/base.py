"""Abstract base class for detectors and a simple registry."""

from __future__ import annotations

import abc

from sentinel.models import DetectorContext, DetectorTier, Finding

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
