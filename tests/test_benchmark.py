"""Tests for the benchmarking module."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from sentinel.core.benchmark import (
    BenchmarkResult,
    DetectorBenchmark,
    _fmt_pct,
    _llm_detector_names,
    compare_benchmarks,
    load_benchmark,
    run_benchmark,
    save_benchmark,
)
from sentinel.detectors.base import Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample-repo"


# ---------------------------------------------------------------------------
# Stub detectors for isolated testing
# ---------------------------------------------------------------------------

class _StubDetector(Detector):
    """Deterministic detector that returns fixed findings."""

    name = "stub-detector"
    description = "test stub"
    tier = DetectorTier.DETERMINISTIC
    categories: ClassVar[list[str]] = ["test"]

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
    categories: ClassVar[list[str]] = ["perf"]

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
    categories: ClassVar[list[str]] = ["error"]

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

    def test_toml_special_characters_roundtrip(self, tmp_path: Path) -> None:
        """Paths and model names with special chars survive roundtrip."""
        result = self._make_result(
            repo_path='/tmp/my "special" repo\\path',
            model='org/model:v1"test',
        )
        toml_str = result.to_toml_str()

        path = tmp_path / "bench.toml"
        path.write_text(toml_str, encoding="utf-8")
        loaded = load_benchmark(path)

        b = loaded["benchmark"]
        assert b["repo_path"] == '/tmp/my "special" repo\\path'
        assert b["model"] == 'org/model:v1"test'

    def test_eval_list_fields_stored_as_counts(self, tmp_path: Path) -> None:
        """List fields in eval results are stored as _count keys."""
        result = self._make_result(
            eval_result={
                "precision": 0.8,
                "recall": 0.6,
                "true_positives": 4,
                "false_positives_found": 1,
                "missing": [{"detector": "x", "title": "y"}],
                "unexpected_fps": ["a", "b"],
            },
        )
        toml_str = result.to_toml_str()

        path = tmp_path / "bench.toml"
        path.write_text(toml_str, encoding="utf-8")
        loaded = load_benchmark(path)

        ev = loaded["benchmark"]["eval"]
        assert ev["missing_count"] == 1
        assert ev["unexpected_fps_count"] == 2
        assert ev["precision"] == 0.8


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


# ── ADR-016: Benchmark-driven prompt strategy tests ───────────────


class TestModelNameToClass:
    """Tests for model_name_to_class()."""

    def test_known_4b_model(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("qwen3.5:4b") == "4b-local"

    def test_known_9b_model(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("qwen3.5:9b-q4_K_M") == "9b-local"

    def test_known_cloud_nano(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("gpt-5.4-nano") == "cloud-nano"

    def test_known_cloud_small(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("gpt-5.4-mini") == "cloud-small"

    def test_known_cloud_frontier(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("claude-sonnet-4.6") == "cloud-frontier"

    def test_bare_gpt54_maps_to_frontier(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("gpt-5.4") == "cloud-frontier"

    def test_sonnet4_non_versioned(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("claude-sonnet-4") == "cloud-frontier"

    def test_case_insensitive(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("GPT-5.4-NANO") == "cloud-nano"

    def test_unknown_model_returns_none(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("llama3.3:70b") is None

    def test_empty_string(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("") is None

    def test_nano_not_matched_by_gpt54(self) -> None:
        """gpt-5.4-nano should match cloud-nano, not cloud-frontier (gpt-5.4)."""
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("gpt-5.4-nano") == "cloud-nano"

    def test_haiku_variant(self) -> None:
        from sentinel.core.compatibility import model_name_to_class
        assert model_name_to_class("claude-haiku-4.5") == "cloud-small"


class TestGetReferenceQuality:
    """Tests for get_reference_quality()."""

    def test_known_good_combo(self) -> None:
        from sentinel.core.compatibility import QualityRating, get_reference_quality
        q = get_reference_quality("qwen3.5:4b", "semantic-drift")
        assert q == QualityRating.GOOD

    def test_known_poor_combo(self) -> None:
        from sentinel.core.compatibility import QualityRating, get_reference_quality
        q = get_reference_quality("qwen3.5:4b", "test-coherence")
        assert q == QualityRating.POOR

    def test_unknown_model(self) -> None:
        from sentinel.core.compatibility import get_reference_quality
        assert get_reference_quality("llama3.3:70b", "semantic-drift") is None

    def test_deterministic_detector_returns_none(self) -> None:
        """Deterministic detectors have NA rating which should return None."""
        from sentinel.core.compatibility import get_reference_quality
        assert get_reference_quality("qwen3.5:4b", "lint-runner") is None


class TestGetEnhancedQuality:
    """Tests for get_enhanced_quality() — checks standard-tier (enhanced mode) ratings."""

    def test_untested_enhanced_returns_none(self) -> None:
        """All current enhanced-mode entries are UNTESTED → None."""
        from sentinel.core.compatibility import get_enhanced_quality
        assert get_enhanced_quality("gpt-5.4-nano", "semantic-drift") is None

    def test_unknown_model_returns_none(self) -> None:
        from sentinel.core.compatibility import get_enhanced_quality
        assert get_enhanced_quality("llama3.3:70b", "semantic-drift") is None

    def test_4b_enhanced_untested(self) -> None:
        """4B has no standard-tier entry → None."""
        from sentinel.core.compatibility import get_enhanced_quality
        assert get_enhanced_quality("qwen3.5:4b", "semantic-drift") is None

    def test_deterministic_detector(self) -> None:
        """Deterministic detectors have no standard-tier entry."""
        from sentinel.core.compatibility import get_enhanced_quality
        assert get_enhanced_quality("gpt-5.4-nano", "lint-runner") is None


class TestShouldUseEnhancedPrompt:
    """Tests for should_use_enhanced_prompt() — ADR-016 core logic."""

    def test_known_good_model_uses_binary_when_enhanced_untested(self) -> None:
        """semantic-drift + 4B: basic quality=GOOD but enhanced=UNTESTED → binary."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        # 4B has GOOD quality at basic tier, but enhanced mode is untested
        assert should_use_enhanced_prompt("qwen3.5:4b", "semantic-drift", "basic") is False

    def test_known_poor_model_uses_binary(self) -> None:
        """test-coherence + 4B = POOR at basic, UNTESTED enhanced → binary."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        assert should_use_enhanced_prompt("qwen3.5:4b", "test-coherence", "basic") is False

    def test_unknown_model_falls_back_to_tier(self) -> None:
        """Unknown model + basic tier → binary (default safe)."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        assert should_use_enhanced_prompt("llama3.3:70b", "semantic-drift", "basic") is False

    def test_unknown_model_standard_override(self) -> None:
        """Unknown model + standard tier → enhanced (explicit override)."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        assert should_use_enhanced_prompt("llama3.3:70b", "semantic-drift", "standard") is True

    def test_unknown_model_advanced_override(self) -> None:
        """Unknown model + advanced tier → enhanced (explicit override)."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        assert should_use_enhanced_prompt("llama3.3:70b", "test-coherence", "advanced") is True

    def test_known_model_untested_enhanced_falls_back_to_tier(self) -> None:
        """cloud-nano + semantic-drift: enhanced=UNTESTED → fall back to tier (basic → False)."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        # cloud-nano has excellent basic quality but enhanced is UNTESTED
        assert should_use_enhanced_prompt("gpt-5.4-nano", "semantic-drift", "basic") is False
        # With explicit standard tier override → True
        assert should_use_enhanced_prompt("gpt-5.4-nano", "semantic-drift", "standard") is True

    def test_fair_quality_uses_binary(self) -> None:
        """test-coherence + 9B: enhanced untested → falls back to tier."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        assert should_use_enhanced_prompt("qwen3.5:9b-q4_K_M", "test-coherence", "basic") is False

    def test_empty_model_string(self) -> None:
        """Empty model string falls back to tier."""
        from sentinel.core.compatibility import should_use_enhanced_prompt
        assert should_use_enhanced_prompt("", "semantic-drift", "basic") is False
        assert should_use_enhanced_prompt("", "semantic-drift", "standard") is True


# ---------------------------------------------------------------------------
# Tests for per-category precision split
# ---------------------------------------------------------------------------


class TestCategorySplit:
    """Tests for _llm_detector_names, _fmt_pct, and category-split TOML output."""

    def test_llm_detector_names_mixed_tiers(self) -> None:
        """_llm_detector_names returns only LLM-assisted detector names."""
        dets = [
            DetectorBenchmark("lint-runner", 3, 50, ["code"], "deterministic"),
            DetectorBenchmark("complexity", 2, 10, ["code"], "heuristic"),
            DetectorBenchmark("semantic-drift", 1, 500, ["docs"], "llm-assisted"),
            DetectorBenchmark("test-coherence", 2, 800, ["test"], "llm-assisted"),
        ]
        result = _llm_detector_names(dets)
        assert result == {"semantic-drift", "test-coherence"}

    def test_llm_detector_names_all_deterministic(self) -> None:
        """Empty set when no LLM detectors."""
        dets = [
            DetectorBenchmark("lint-runner", 3, 50, ["code"], "deterministic"),
            DetectorBenchmark("complexity", 2, 10, ["code"], "heuristic"),
        ]
        assert _llm_detector_names(dets) == set()

    def test_fmt_pct_float(self) -> None:
        assert _fmt_pct(0.85) == "85.00%"

    def test_fmt_pct_int(self) -> None:
        assert _fmt_pct(1) == "100.00%"

    def test_fmt_pct_none(self) -> None:
        assert _fmt_pct(None) == "—"

    def test_toml_category_split_roundtrip(self) -> None:
        """TOML output includes deterministic/llm sections that roundtrip."""
        import tomllib

        result = BenchmarkResult(
            repo_path="/tmp/test",
            timestamp="2026-04-13T00:00:00Z",
            model="test",
            provider="test",
            model_capability="basic",
            total_findings=6,
            total_duration_ms=1000,
            detector_count=3,
            detectors=[
                DetectorBenchmark("lint-runner", 3, 50, ["code"], "deterministic"),
                DetectorBenchmark("semantic-drift", 2, 500, ["docs"], "llm-assisted"),
                DetectorBenchmark("todo-scanner", 1, 10, ["todo"], "deterministic"),
            ],
            eval_result={
                "total_findings": 6,
                "true_positives": 5,
                "false_positives_found": 0,
                "missing": [],
                "unexpected_fps": [],
                "precision": 0.8333,
                "recall": 1.0,
                "per_detector": {
                    "lint-runner": {
                        "total_findings": 3, "true_positives": 3,
                        "expected": 3, "precision": 1.0, "recall": 1.0,
                    },
                    "semantic-drift": {
                        "total_findings": 2, "true_positives": 1,
                        "expected": 1, "precision": 0.5, "recall": 1.0,
                    },
                    "todo-scanner": {
                        "total_findings": 1, "true_positives": 1,
                        "expected": 1, "precision": 1.0, "recall": 1.0,
                    },
                },
            },
        )

        toml_str = result.to_toml_str()
        parsed = tomllib.loads(toml_str)

        det = parsed["benchmark"]["eval"]["deterministic"]
        assert det["findings"] == 4  # lint-runner(3) + todo-scanner(1)
        assert det["true_positives"] == 4
        assert det["precision"] == 1.0

        llm = parsed["benchmark"]["eval"]["llm_assisted"]
        assert llm["findings"] == 2
        assert llm["true_positives"] == 1
        assert llm["precision"] == 0.5

        # Per-detector sections
        pd = parsed["benchmark"]["eval"]["per_detector"]
        assert "lint-runner" in pd
        assert "semantic-drift" in pd
        assert pd["semantic-drift"]["precision"] == 0.5

    def test_toml_no_eval_skips_split(self) -> None:
        """No eval_result means no deterministic/llm sections."""
        result = BenchmarkResult(
            repo_path="/tmp/test",
            timestamp="2026-04-13T00:00:00Z",
            model="test",
            provider="test",
            model_capability="basic",
            total_findings=1,
            total_duration_ms=100,
            detector_count=1,
            detectors=[
                DetectorBenchmark("lint-runner", 1, 50, ["code"], "deterministic"),
            ],
            eval_result=None,
        )
        toml_str = result.to_toml_str()
        assert "[benchmark.eval.deterministic]" not in toml_str
        assert "[benchmark.eval.llm_assisted]" not in toml_str
