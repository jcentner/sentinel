"""Tests for detector base class and registry."""

import pytest

from sentinel.detectors.base import (
    _REGISTRY,
    Detector,
    get_all_detectors,
    get_detector,
    get_registry,
    load_custom_detectors,
    load_entrypoint_detectors,
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


class TestLoadEntrypointDetectors:
    """Tests for entry_points-based detector discovery (ADR-012)."""

    def test_no_entry_points_returns_empty(self, monkeypatch):
        """When no entry points exist, returns empty list."""
        monkeypatch.setattr(
            "sentinel.detectors.base.entry_points",
            lambda group: [],
        )
        loaded = load_entrypoint_detectors()
        assert loaded == []

    def test_loads_entry_point_detector(self, monkeypatch):
        """A working entry point registers its detector."""
        from unittest.mock import MagicMock

        # Create a mock entry point that, when loaded, registers a new detector
        mock_ep = MagicMock()
        mock_ep.name = "ep-detector"
        mock_ep.value = "some_package.module"

        # When ep.load() is called, register a detector
        def _load_side_effect():
            # Simulate what happens when a module with a Detector subclass is imported
            _REGISTRY["ep-test-det"] = _StubDetector  # type: ignore[assignment]
        mock_ep.load = _load_side_effect

        monkeypatch.setattr(
            "sentinel.detectors.base.entry_points",
            lambda group: [mock_ep],
        )

        loaded = load_entrypoint_detectors()
        assert "ep-test-det" in loaded

        # Clean up
        _REGISTRY.pop("ep-test-det", None)

    def test_broken_entry_point_skipped(self, monkeypatch, caplog):
        """A broken entry point is skipped with a warning."""
        import logging
        from unittest.mock import MagicMock

        mock_ep = MagicMock()
        mock_ep.name = "broken-ep"
        mock_ep.value = "broken_package.module"
        mock_ep.load.side_effect = ImportError("No such module")

        monkeypatch.setattr(
            "sentinel.detectors.base.entry_points",
            lambda group: [mock_ep],
        )

        with caplog.at_level(logging.WARNING):
            loaded = load_entrypoint_detectors()

        assert loaded == []
        assert "broken-ep" in caplog.text

    def test_builtin_name_collision_keeps_builtin(self, monkeypatch, caplog):
        """Entry point with same name as built-in is skipped."""
        import logging
        from unittest.mock import MagicMock

        # stub-detector is already registered (from _StubDetector class above)
        assert "stub-detector" in _REGISTRY

        mock_ep = MagicMock()
        mock_ep.name = "stub-detector"
        mock_ep.value = "some_package.stub"

        def _load_side_effect():
            # This would try to re-register stub-detector, but it's already there
            pass
        mock_ep.load = _load_side_effect

        monkeypatch.setattr(
            "sentinel.detectors.base.entry_points",
            lambda group: [mock_ep],
        )

        with caplog.at_level(logging.WARNING):
            loaded = load_entrypoint_detectors()

        # stub-detector should NOT appear in loaded (it's a built-in collision)
        assert "stub-detector" not in loaded
