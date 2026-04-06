"""Tests for detector base class and registry."""

import pytest

from sentinel.detectors.base import (
    _REGISTRY,
    Detector,
    get_all_detectors,
    get_detector,
    get_registry,
    load_custom_detectors,
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


class TestLoadCustomDetectors:
    """Tests for loading custom detector plugins from a directory."""

    def _write_custom_detector(self, directory, name="my_detector", tag="custom-test"):
        """Write a valid custom detector Python file."""
        code = f'''
from sentinel.detectors.base import Detector
from sentinel.models import DetectorContext, DetectorTier, Finding

class CustomDetector(Detector):
    @property
    def name(self): return "{tag}"
    @property
    def description(self): return "A custom detector"
    @property
    def tier(self): return DetectorTier.DETERMINISTIC
    @property
    def categories(self): return ["custom"]
    def detect(self, context):
        return []
'''
        (directory / f"{name}.py").write_text(code)

    def test_loads_detector_from_directory(self, tmp_path):
        self._write_custom_detector(tmp_path)
        before = set(_REGISTRY.keys())
        loaded = load_custom_detectors(tmp_path)
        after = set(_REGISTRY.keys())
        assert "custom-test" in loaded
        assert "custom-test" in after - before
        # Clean up
        del _REGISTRY["custom-test"]

    def test_returns_empty_for_nonexistent_dir(self, tmp_path):
        loaded = load_custom_detectors(tmp_path / "nonexistent")
        assert loaded == []

    def test_skips_underscore_files(self, tmp_path):
        self._write_custom_detector(tmp_path, name="_private", tag="private-det")
        loaded = load_custom_detectors(tmp_path)
        assert "private-det" not in loaded

    def test_skips_broken_files(self, tmp_path):
        (tmp_path / "broken.py").write_text("raise RuntimeError('boom')")
        loaded = load_custom_detectors(tmp_path)
        assert loaded == []

    def test_multiple_detectors(self, tmp_path):
        self._write_custom_detector(tmp_path, name="det_a", tag="custom-a")
        self._write_custom_detector(tmp_path, name="det_b", tag="custom-b")
        loaded = load_custom_detectors(tmp_path)
        assert "custom-a" in loaded
        assert "custom-b" in loaded
        # Clean up
        _REGISTRY.pop("custom-a", None)
        _REGISTRY.pop("custom-b", None)
