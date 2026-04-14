"""Tests for the pipeline runner."""

from __future__ import annotations

import pytest

from sentinel.core.runner import run_scan
from sentinel.detectors.base import Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)


class _MockDetector(Detector):
    """A mock detector that returns canned findings."""

    def __init__(self, findings: list[Finding] | None = None):
        self._findings = findings or []

    @property
    def name(self) -> str:
        return "mock-detector"

    @property
    def description(self) -> str:
        return "Mock"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["test"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        return self._findings


class _FailingDetector(Detector):
    """A detector that always raises."""

    @property
    def name(self) -> str:
        return "failing-detector"

    @property
    def description(self) -> str:
        return "Fails"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["test"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        raise RuntimeError("Intentional failure")


def _sample_finding(title: str = "Test finding") -> Finding:
    return Finding(
        detector="mock-detector",
        category="test",
        severity=Severity.MEDIUM,
        confidence=0.8,
        title=title,
        description="A test finding",
        evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="bad")],
        file_path="x.py",
        line_start=1,
    )


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "x.py").write_text("# some code\n")
    return tmp_path


class TestRunner:
    def test_full_pipeline(self, db_conn, repo):
        detector = _MockDetector([_sample_finding()])
        run, findings, report = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        assert run.id is not None
        assert len(findings) == 1
        assert "Test finding" in report

    def test_empty_findings(self, db_conn, repo):
        detector = _MockDetector([])
        _run, findings, report = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        assert len(findings) == 0
        assert "No issues found" in report

    def test_failing_detector_isolated(self, db_conn, repo):
        """A failing detector should not abort the run."""
        good = _MockDetector([_sample_finding()])
        bad = _FailingDetector()
        _run, findings, _report = run_scan(
            str(repo), db_conn,
            detectors=[bad, good],
            skip_judge=True,
        )
        assert len(findings) == 1  # Good detector's findings survive

    def test_deduplication_across_runs(self, db_conn, repo):
        detector = _MockDetector([_sample_finding()])

        # First run
        _run1, _findings1, _ = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )

        # Second run — same finding should be marked recurring
        _run2, findings2, _ = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        assert len(findings2) == 1
        assert findings2[0].context.get("recurring") is True

    def test_report_written_to_disk(self, db_conn, repo, tmp_path):
        out = tmp_path / "output" / "report.md"
        detector = _MockDetector([_sample_finding()])
        run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
            output_path=str(out),
        )
        assert out.exists()

    def test_run_record_completed(self, db_conn, repo):
        detector = _MockDetector([_sample_finding()])
        run, _, _ = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
        )
        from sentinel.store.runs import get_run_by_id
        updated = get_run_by_id(db_conn, run.id)
        assert updated.completed_at is not None
        assert updated.finding_count == 1

    def test_targeted_scan(self, db_conn, repo):
        """Targeted scan passes target_paths to detectors and uses TARGETED scope."""
        from sentinel.models import ScopeType

        captured_ctx = {}

        class _CapturingDetector(_MockDetector):
            def detect(self, context: DetectorContext) -> list[Finding]:
                captured_ctx["scope"] = context.scope
                captured_ctx["target_paths"] = context.target_paths
                return super().detect(context)

        detector = _CapturingDetector([_sample_finding()])
        run, findings, _report = run_scan(
            str(repo), db_conn,
            detectors=[detector],
            skip_judge=True,
            scope=ScopeType.TARGETED,
            target_paths=["x.py"],
        )
        assert run.id is not None
        assert len(findings) == 1
        assert captured_ctx["scope"] == ScopeType.TARGETED
        assert captured_ctx["target_paths"] == ["x.py"]


class TestDetectorFiltering:
    """Tests for enabled_detectors / disabled_detectors filtering."""

    def test_enabled_detectors_filter(self, db_conn, repo):
        """Only run detectors in the enabled list."""
        class _DetA(_MockDetector):
            @property
            def name(self):
                return "det-a"
            def detect(self, ctx):
                return [Finding(
                    detector="det-a", category="test", severity=Severity.LOW,
                    confidence=1.0, title="From A", description="a",
                    evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="a")],
                )]

        class _DetB(_MockDetector):
            @property
            def name(self):
                return "det-b"
            def detect(self, ctx):
                return [Finding(
                    detector="det-b", category="test", severity=Severity.LOW,
                    confidence=1.0, title="From B", description="b",
                    evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="b")],
                )]

        _run, findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[_DetA(), _DetB()],
            skip_judge=True,
            enabled_detectors=["det-a"],
        )
        assert len(findings) == 1
        assert findings[0].detector == "det-a"

    def test_disabled_detectors_filter(self, db_conn, repo):
        """Skip detectors in the disabled list."""
        class _DetC(_MockDetector):
            @property
            def name(self):
                return "det-c"
            def detect(self, ctx):
                return [Finding(
                    detector="det-c", category="test", severity=Severity.LOW,
                    confidence=1.0, title="From C", description="c",
                    evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="c")],
                )]

        class _DetD(_MockDetector):
            @property
            def name(self):
                return "det-d"
            def detect(self, ctx):
                return [Finding(
                    detector="det-d", category="test", severity=Severity.LOW,
                    confidence=1.0, title="From D", description="d",
                    evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="d")],
                )]

        _run, findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[_DetC(), _DetD()],
            skip_judge=True,
            disabled_detectors=["det-c"],
        )
        assert len(findings) == 1
        assert findings[0].detector == "det-d"

    def test_no_filter_runs_all(self, db_conn, repo):
        """Without filters, all detectors run."""
        det = _MockDetector([_sample_finding()])
        _run, findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[det],
            skip_judge=True,
        )
        assert len(findings) == 1

    def test_unknown_enabled_detector_warns(self, db_conn, repo, caplog):
        """Unknown names in enabled_detectors produce a warning."""
        import logging
        det = _MockDetector([_sample_finding()])
        with caplog.at_level(logging.WARNING):
            _run, findings, _ = run_scan(
                str(repo), db_conn,
                detectors=[det],
                skip_judge=True,
                enabled_detectors=["mock-detector", "nonexistent"],
            )
        assert len(findings) == 1
        assert "nonexistent" in caplog.text

    def test_min_confidence_filters_report(self, db_conn, repo):
        """Findings below min_confidence are stored but excluded from report."""
        low_conf = Finding(
            detector="mock-detector", category="test",
            severity=Severity.MEDIUM, confidence=0.2,
            title="Low confidence finding",
            description="Should be filtered from report",
            evidence=[], file_path="x.py", line_start=1,
        )
        high_conf = _sample_finding(title="High confidence finding")

        det = _MockDetector([low_conf, high_conf])
        _run, findings, report = run_scan(
            str(repo), db_conn,
            detectors=[det],
            skip_judge=True,
            min_confidence=0.5,
        )
        # Both findings are persisted in the DB
        assert len(findings) == 2
        # But the report only contains the high-confidence one
        assert "High confidence finding" in report
        assert "Low confidence finding" not in report

    def test_min_confidence_zero_shows_all(self, db_conn, repo):
        """min_confidence=0 (default) shows all findings."""
        low_conf = Finding(
            detector="mock-detector", category="test",
            severity=Severity.LOW, confidence=0.1,
            title="Very low",
            description="Still shown",
            evidence=[], file_path="x.py", line_start=1,
        )
        det = _MockDetector([low_conf])
        _run, findings, report = run_scan(
            str(repo), db_conn,
            detectors=[det],
            skip_judge=True,
            min_confidence=0.0,
        )
        assert len(findings) == 1
        assert "Very low" in report

    def test_enabled_by_default_excludes_non_default(self, db_conn, repo, caplog):
        """Detectors with enabled_by_default=False are excluded without explicit filter."""
        import logging

        class _OptInDetector(_MockDetector):
            @property
            def name(self):
                return "opt-in-det"

            @property
            def enabled_by_default(self):
                return False

            def detect(self, ctx):
                return [Finding(
                    detector="opt-in-det", category="test",
                    severity=Severity.LOW, confidence=1.0,
                    title="From opt-in", description="opt-in",
                    evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="a")],
                )]

        default_det = _MockDetector([_sample_finding()])
        with caplog.at_level(logging.INFO):
            _run, findings, _ = run_scan(
                str(repo), db_conn,
                detectors=[default_det, _OptInDetector()],
                skip_judge=True,
            )
        assert len(findings) == 1
        assert findings[0].detector == "mock-detector"
        assert "opt-in-det" in caplog.text

    def test_enabled_by_default_included_when_explicitly_enabled(self, db_conn, repo):
        """Detectors with enabled_by_default=False run when in enabled_detectors."""
        class _OptInDetector(_MockDetector):
            @property
            def name(self):
                return "opt-in-det"

            @property
            def enabled_by_default(self):
                return False

            def detect(self, ctx):
                return [Finding(
                    detector="opt-in-det", category="test",
                    severity=Severity.LOW, confidence=1.0,
                    title="From opt-in", description="opt-in",
                    evidence=[Evidence(type=EvidenceType.CODE, source="x.py", content="a")],
                )]

        _run, findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[_MockDetector([_sample_finding()]), _OptInDetector()],
            skip_judge=True,
            enabled_detectors=["opt-in-det"],
        )
        assert len(findings) == 1
        assert findings[0].detector == "opt-in-det"


# ── Per-detector provider (OQ-012) ──────────────────────────────────


class _ProviderCapturingDetector(Detector):
    """Captures the provider from context during detect()."""

    def __init__(self, det_name: str = "capturing-detector"):
        self._name = det_name
        self.captured_provider = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Captures provider"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["test"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        self.captured_provider = context.config.get("provider")
        return []


class _FailingCapturingDetector(Detector):
    """Captures provider then raises — tests exception-safe restore."""

    def __init__(self, det_name: str = "failing-capture"):
        self._name = det_name
        self.captured_provider = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Captures then fails"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["test"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        self.captured_provider = context.config.get("provider")
        raise RuntimeError("Intentional failure after capture")


class TestPerDetectorProvider:
    def test_per_detector_provider_swapped(self, db_conn, repo):
        """Detector with an override sees the overridden provider."""
        from unittest.mock import MagicMock

        from sentinel.config import ProviderOverride, SentinelConfig

        global_provider = MagicMock()
        global_provider.check_health.return_value = True
        override_provider = MagicMock()
        override_provider.check_health.return_value = True

        sentinel_config = SentinelConfig(
            provider="ollama",
            model="qwen3.5:4b",
            detector_providers={
                "det-a": ProviderOverride(model="llama3:8b"),
            },
        )

        det_a = _ProviderCapturingDetector("det-a")
        det_b = _ProviderCapturingDetector("det-b")

        # skip_judge=False so per-detector providers are built.
        # Detectors return [] so the judge has nothing to do.
        from unittest.mock import patch
        with patch(
            "sentinel.core.provider.create_provider_for_detector",
            side_effect=lambda name, cfg: override_provider if name == "det-a" else None,
        ):
            _run, _findings, _ = run_scan(
                str(repo), db_conn,
                detectors=[det_a, det_b],
                provider=global_provider,
                skip_judge=False,
                sentinel_config=sentinel_config,
            )

        # det_a should have seen the override provider
        assert det_a.captured_provider is override_provider
        # det_b should have seen the global provider
        assert det_b.captured_provider is global_provider

    def test_provider_restored_after_detector_failure(self, db_conn, repo):
        """Global provider is restored even when a per-detector detector raises."""
        from unittest.mock import MagicMock, patch

        from sentinel.config import ProviderOverride, SentinelConfig

        global_provider = MagicMock()
        override_provider = MagicMock()

        sentinel_config = SentinelConfig(
            provider="ollama",
            model="qwen3.5:4b",
            detector_providers={
                "failing-capture": ProviderOverride(model="llama3:8b"),
            },
        )

        failing = _FailingCapturingDetector("failing-capture")
        normal = _ProviderCapturingDetector("normal-detector")

        with patch(
            "sentinel.core.provider.create_provider_for_detector",
            side_effect=lambda name, cfg: override_provider if name == "failing-capture" else None,
        ):
            _run, _findings, _ = run_scan(
                str(repo), db_conn,
                detectors=[failing, normal],
                provider=global_provider,
                skip_judge=False,
                sentinel_config=sentinel_config,
            )

        # failing detector saw override
        assert failing.captured_provider is override_provider
        # normal detector should see global (restored after failure)
        assert normal.captured_provider is global_provider

    def test_no_swap_when_no_overrides(self, db_conn, repo):
        """Without sentinel_config, all detectors see the same provider."""
        from unittest.mock import MagicMock

        global_provider = MagicMock()

        det_a = _ProviderCapturingDetector("det-a")
        det_b = _ProviderCapturingDetector("det-b")

        _run, _findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[det_a, det_b],
            provider=global_provider,
            skip_judge=True,
        )

        assert det_a.captured_provider is global_provider
        assert det_b.captured_provider is global_provider


# ── TD-043: Two-phase execution and risk signals ────────────────────


class _LLMDetector(_MockDetector):
    """Mock LLM-assisted detector that records the context it receives."""

    captured_risk_signals: dict | None = None

    @property
    def name(self) -> str:
        return "mock-llm"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.LLM_ASSISTED

    def detect(self, context: DetectorContext) -> list[Finding]:
        self.captured_risk_signals = context.risk_signals
        return self._findings


class _HeuristicDetector(_MockDetector):
    """Mock heuristic detector that produces hotspot-like findings."""

    @property
    def name(self) -> str:
        return "mock-heuristic"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.HEURISTIC


class TestTwoPhaseExecution:
    """Tests for TD-043: two-phase detector execution with risk signals."""

    def test_heuristic_runs_before_llm(self, db_conn, repo):
        """Heuristic detectors run in phase 1, LLM detectors in phase 2."""
        execution_order: list[str] = []

        class _OrderTracker(_MockDetector):
            def detect(self, ctx):
                execution_order.append(self.name)
                return []

        class _HeuristicTracker(_OrderTracker):
            @property
            def name(self):
                return "heuristic-first"
            @property
            def tier(self):
                return DetectorTier.HEURISTIC

        class _LLMTracker(_OrderTracker):
            @property
            def name(self):
                return "llm-second"
            @property
            def tier(self):
                return DetectorTier.LLM_ASSISTED

        # Put LLM detector first in the list — should still run second
        _run, _findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[_LLMTracker(), _HeuristicTracker()],
            skip_judge=True,
        )
        assert execution_order == ["heuristic-first", "llm-second"]

    def test_risk_signals_from_hotspot_findings(self, db_conn, repo):
        """Risk signals are built from git-hotspots findings with context."""
        hotspot_finding = Finding(
            detector="git-hotspots",
            category="git-health",
            severity=Severity.MEDIUM,
            confidence=0.8,
            title="High-churn: src/main.py",
            description="High churn",
            evidence=[],
            file_path="src/main.py",
            context={
                "churn_commits": 25,
                "churn_fix_ratio": 0.6,
                "author_count": 3,
            },
        )

        heuristic = _HeuristicDetector([hotspot_finding])
        llm = _LLMDetector([])

        _run, _findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[heuristic, llm],
            skip_judge=True,
        )

        assert llm.captured_risk_signals is not None
        assert "src/main.py" in llm.captured_risk_signals
        sig = llm.captured_risk_signals["src/main.py"]
        assert sig["is_hotspot"] is True
        assert sig["churn_commits"] == 25
        assert sig["churn_fix_ratio"] == 0.6

    def test_no_risk_signals_when_no_hotspots(self, db_conn, repo):
        """LLM detectors get None risk_signals when no hotspots found."""
        heuristic = _MockDetector([])  # No findings
        llm = _LLMDetector([])

        _run, _findings, _ = run_scan(
            str(repo), db_conn,
            detectors=[heuristic, llm],
            skip_judge=True,
        )

        # No hotspot findings → empty signals → risk_signals stays None
        assert llm.captured_risk_signals is None


class TestBuildRiskSignals:
    """Tests for _build_risk_signals helper."""

    def test_extracts_hotspot_signals(self):
        from sentinel.core.runner import _build_risk_signals

        findings = [
            Finding(
                detector="git-hotspots",
                category="git-health",
                severity=Severity.LOW,
                confidence=0.5,
                title="hotspot",
                description="",
                evidence=[],
                file_path="lib/core.py",
                context={
                    "churn_commits": 40,
                    "churn_fix_ratio": 0.3,
                    "author_count": 2,
                },
            ),
        ]
        signals = _build_risk_signals(findings)
        assert "lib/core.py" in signals
        assert signals["lib/core.py"]["is_hotspot"] is True
        assert signals["lib/core.py"]["churn_commits"] == 40

    def test_ignores_non_hotspot_findings(self):
        from sentinel.core.runner import _build_risk_signals

        findings = [
            Finding(
                detector="lint-runner",
                category="code-quality",
                severity=Severity.LOW,
                confidence=0.9,
                title="lint issue",
                description="",
                evidence=[],
                file_path="lib/core.py",
            ),
        ]
        signals = _build_risk_signals(findings)
        assert signals == {}

    def test_ignores_findings_without_context(self):
        from sentinel.core.runner import _build_risk_signals

        findings = [
            Finding(
                detector="git-hotspots",
                category="git-health",
                severity=Severity.LOW,
                confidence=0.5,
                title="hotspot",
                description="",
                evidence=[],
                file_path="lib/core.py",
                context=None,
            ),
        ]
        signals = _build_risk_signals(findings)
        assert signals == {}

    def test_empty_findings(self):
        from sentinel.core.runner import _build_risk_signals

        assert _build_risk_signals([]) == {}
