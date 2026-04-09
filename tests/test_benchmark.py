"""Tests for the benchmarking module."""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel.core.benchmark import (
    BenchmarkResult,
    DetectorBenchmark,
    compare_benchmarks,
    load_benchmark,
    run_benchmark,
    save_benchmark,
)
from sentinel.detectors.base import Detector
from sentinel.models import DetectorContext, DetectorTier, Evidence, EvidenceType, Finding, Severity

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample-repo"


# ---------------------------------------------------------------------------
# Stub detectors for isolated testing
# ---------------------------------------------------------------------------

class _StubDetector(Detector):
    """Deterministic detector that returns fixed findings."""

    name = "stub-detector"
    description = "test stub"
    tier = DetectorTier.DETERMINISTIC
    categories = ["test"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        return [
            Finding(
                detector="stub-detector",
                title="stub finding",
                description="desc",
                file_path="a.py",
                severity=Severity.LOW,
                confidence=1.0,
                category="test",
                evidence=[Evidence(type=EvidenceType.CODE, source="test", content="e")],
            ),
        ]


class _SlowStubDetector(Detector):
    """Detector that returns two findings."""

    name = "slow-stub"
    description = "slow test stub"
    tier = DetectorTier.HEURISTIC
    categories = ["perf"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        return [
            Finding(
                detector="slow-stub",
                title="perf-1",
                description="d",
                file_path="b.py",
                severity=Severity.MEDIUM,
                confidence=0.8,
                category="perf",
                evidence=[Evidence(type=EvidenceType.CODE, source="test", content="e")],
            ),
            Finding(
                detector="slow-stub",
                title="perf-2",
                description="d",
                file_path="c.py",
                severity=Severity.HIGH,
                confidence=0.9,
                category="perf",
                evidence=[Evidence(type=EvidenceType.CODE, source="test", content="e")],
            ),
        ]


class _FailingStubDetector(Detector):
    """Detector that raises an exception."""

    name = "failing-stub"
    description = "always fails"
    tier = DetectorTier.DETERMINISTIC
    categories = ["error"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        msg = "intentional failure"
        raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunBenchmark:
    """Tests for run_benchmark()."""

    def test_basic_run_with_stub_detectors(self, tmp_path: Path) -> None:
        """Run benchmark with explicit detectors list."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "test.py").write_text("x = 1\n")

        result = run_benchmark(
            str(repo),
            model="test-model",
            provider_name="test-provider",
            detectors=[_StubDetector(), _SlowStubDetector()],
        )

        assert result.model == "test-model"
        assert result.provider == "test-provider"
        assert result.total_findings == 3  # 1 + 2
        assert result.detector_count == 2
        assert len(result.detectors) == 2
        assert result.total_duration_ms >= 0

    def test_failing_detector_recorded(self, tmp_path: Path) -> None:
        """A failing detector gets finding_count=-1 instead of crashing the run."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "test.py").write_text("x = 1\n")

        result = run_benchmark(
            str(repo),
            detectors=[_FailingStubDetector(), _StubDetector()],
        )

        assert result.total_findings == 1  # Only from stub
        failing = next(d for d in result.detectors if d.name == "failing-stub")
        assert failing.finding_count == -1
        assert failing.duration_ms >= 0

    def test_enabled_filter(self, tmp_path: Path) -> None:
        """Only enabled detectors run."""
        repo = tmp_path / "repo"
        repo.mkdir()

        result = run_benchmark(
            str(repo),
            detectors=[_StubDetector(), _SlowStubDetector()],
            enabled_detectors=["stub-detector"],
        )

        assert result.detector_count == 1
        assert result.total_findings == 1

    def test_disabled_filter(self, tmp_path: Path) -> None:
        """Disabled detectors are skipped."""
        repo = tmp_path / "repo"
        repo.mkdir()

        result = run_benchmark(
            str(repo),
            detectors=[_StubDetector(), _SlowStubDetector()],
            disabled_detectors=["slow-stub"],
        )

        assert result.detector_count == 1
        assert result.total_findings == 1

    def test_ground_truth_eval(self) -> None:
        """Ground truth evaluation populates eval_result when available."""
        if not FIXTURE_DIR.exists():
            pytest.skip("sample-repo fixture not found")

        gt_path = FIXTURE_DIR / "ground-truth.toml"
        if not gt_path.exists():
            pytest.skip("ground-truth.toml not found")

        result = run_benchmark(
            str(FIXTURE_DIR),
            skip_judge=True,
            detectors=[_StubDetector()],
            ground_truth_path=str(gt_path),
        )

        # Eval should be populated (stub detector won't match ground truth)
        assert result.eval_result is not None
        assert "precision" in result.eval_result

    def test_missing_ground_truth_ignored(self, tmp_path: Path) -> None:
        """Non-existent ground truth path is logged and ignored."""
        repo = tmp_path / "repo"
        repo.mkdir()

        result = run_benchmark(
            str(repo),
            detectors=[_StubDetector()],
            ground_truth_path="/nonexistent/ground-truth.toml",
        )

        assert result.eval_result is None


class TestBenchmarkResult:
    """Tests for BenchmarkResult serialization."""

    def _make_result(self, **kwargs: object) -> BenchmarkResult:
        defaults = {
            "repo_path": "/tmp/repo",
            "timestamp": "2025-01-15T10:30:00Z",
            "model": "qwen3.5:4b",
            "provider": "ollama",
            "model_capability": "basic",
            "total_findings": 5,
            "total_duration_ms": 1234.5,
            "detector_count": 2,
            "detectors": [
                DetectorBenchmark(
                    name="todo-scanner",
                    finding_count=3,
                    duration_ms=100.0,
                    categories=["code-quality"],
                    tier="deterministic",
                ),
                DetectorBenchmark(
                    name="lint-runner",
                    finding_count=2,
                    duration_ms=200.0,
                    categories=["code-quality"],
                    tier="deterministic",
                ),
            ],
            "eval_result": None,
        }
        defaults.update(kwargs)
        return BenchmarkResult(**defaults)

    def test_toml_serialization_roundtrip(self, tmp_path: Path) -> None:
        """TOML output can be parsed back."""
        result = self._make_result()
        toml_str = result.to_toml_str()

        # Write and reload
        path = tmp_path / "bench.toml"
        path.write_text(toml_str, encoding="utf-8")
        loaded = load_benchmark(path)

        b = loaded["benchmark"]
        assert b["model"] == "qwen3.5:4b"
        assert b["provider"] == "ollama"
        assert b["total_findings"] == 5
        assert len(b["detectors"]) == 2

    def test_toml_contains_expected_fields(self) -> None:
        """TOML string contains all required elements."""
        result = self._make_result()
        toml_str = result.to_toml_str()

        assert "[benchmark]" in toml_str
        assert "[[benchmark.detectors]]" in toml_str
        assert 'model = "qwen3.5:4b"' in toml_str
        assert "total_duration_ms = 1234.5" in toml_str

    def test_toml_with_eval_result(self, tmp_path: Path) -> None:
        """TOML includes eval section when present."""
        result = self._make_result(
            eval_result={"precision": 0.75, "recall": 0.5, "true_positives": 3},
        )
        toml_str = result.to_toml_str()

        assert "[benchmark.eval]" in toml_str
        assert "precision = 0.7500" in toml_str
        assert "recall = 0.5000" in toml_str

        # Verify roundtrip
        path = tmp_path / "bench.toml"
        path.write_text(toml_str, encoding="utf-8")
        loaded = load_benchmark(path)
        assert loaded["benchmark"]["eval"]["precision"] == 0.75


class TestSaveBenchmark:
    """Tests for save_benchmark()."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """Saves a TOML file with expected name pattern."""
        result = BenchmarkResult(
            repo_path="/tmp/myrepo",
            timestamp="2025-01-15T10:30:00Z",
            model="qwen3.5:4b",
            provider="ollama",
            model_capability="basic",
            total_findings=1,
            total_duration_ms=100.0,
            detector_count=1,
            detectors=[
                DetectorBenchmark(
                    name="test",
                    finding_count=1,
                    duration_ms=50.0,
                    categories=["test"],
                    tier="deterministic",
                ),
            ],
        )

        saved = save_benchmark(result, str(tmp_path / "out"))
        assert Path(saved).exists()
        assert saved.endswith(".toml")
        assert "myrepo" in Path(saved).name

    def test_creates_output_dir(self, tmp_path: Path) -> None:
        """Output directory is created if it doesn't exist."""
        result = BenchmarkResult(
            repo_path="/tmp/repo",
            timestamp="2025-01-15T10:30:00Z",
            model="m",
            provider="p",
            model_capability="basic",
            total_findings=0,
            total_duration_ms=0,
            detector_count=0,
            detectors=[],
        )

        out = tmp_path / "nested" / "output"
        saved = save_benchmark(result, str(out))
        assert out.exists()
        assert Path(saved).exists()


class TestCompareBenchmarks:
    """Tests for compare_benchmarks()."""

    def _write_bench(self, path: Path, model: str, findings: int) -> Path:
        result = BenchmarkResult(
            repo_path="/tmp/repo",
            timestamp="2025-01-15T10:30:00Z",
            model=model,
            provider="ollama",
            model_capability="basic",
            total_findings=findings,
            total_duration_ms=500.0,
            detector_count=1,
            detectors=[
                DetectorBenchmark(
                    name="todo-scanner",
                    finding_count=findings,
                    duration_ms=500.0,
                    categories=["code-quality"],
                    tier="deterministic",
                ),
            ],
        )
        filepath = path / f"{model}.toml"
        filepath.write_text(result.to_toml_str(), encoding="utf-8")
        return filepath

    def test_compare_two(self, tmp_path: Path) -> None:
        """Comparison table includes both models."""
        a = self._write_bench(tmp_path, "model-a", 5)
        b = self._write_bench(tmp_path, "model-b", 10)

        report = compare_benchmarks([a, b])

        assert "model-a" in report
        assert "model-b" in report
        assert "todo-scanner" in report
        assert "5" in report
        assert "10" in report

    def test_compare_empty(self) -> None:
        """Empty input produces graceful message."""
        report = compare_benchmarks([])
        assert "No benchmark" in report

    def test_compare_single(self, tmp_path: Path) -> None:
        """Single benchmark still produces valid table."""
        a = self._write_bench(tmp_path, "solo-model", 3)
        report = compare_benchmarks([a])
        assert "solo-model" in report
        assert "todo-scanner" in report
