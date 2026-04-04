"""Tests for detector base class and registry."""

import pytest

from sentinel.detectors.base import (
    Detector,
    get_all_detectors,
    get_detector,
    get_registry,
)
from sentinel.models import DetectorContext, DetectorTier, Finding


class _StubDetector(Detector):
    """A concrete detector for testing."""

    @property
    def name(self) -> str:
        return "stub-detector"

    @property
    def description(self) -> str:
        return "A stub for testing"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["code-quality"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        return []


class TestDetectorBase:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            Detector()  # type: ignore[abstract]

    def test_concrete_subclass_registered(self):
        registry = get_registry()
        assert "stub-detector" in registry

    def test_get_all_detectors(self):
        detectors = get_all_detectors()
        names = [d.name for d in detectors]
        assert "stub-detector" in names

    def test_get_detector_by_name(self):
        d = get_detector("stub-detector")
        assert d is not None
        assert d.name == "stub-detector"
        assert d.tier == DetectorTier.DETERMINISTIC

    def test_get_detector_not_found(self):
        assert get_detector("nonexistent") is None

    def test_detect_returns_list(self):
        d = get_detector("stub-detector")
        ctx = DetectorContext(repo_root="/tmp/test")
        result = d.detect(ctx)
        assert isinstance(result, list)
        assert len(result) == 0
