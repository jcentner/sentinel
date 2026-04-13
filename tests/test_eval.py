"""Precision/recall evaluation against the seeded sample-repo fixture.

This test runs the full pipeline against a repo with known ground truth
and verifies that all expected findings are present and no false positives
are produced by the detectors we control (docs-drift, todo-scanner, lint-runner).

Ground truth is defined in tests/fixtures/sample-repo/ground-truth.toml
and shared with the `sentinel eval` CLI command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel.core.eval import evaluate, load_ground_truth
from sentinel.core.runner import run_scan
from sentinel.store.db import get_connection

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample-repo"
GROUND_TRUTH_PATH = FIXTURE_DIR / "ground-truth.toml"


@pytest.fixture(scope="module")
def ground_truth():
    """Load the shared ground truth definition."""
    if not GROUND_TRUTH_PATH.exists():
        pytest.skip("ground-truth.toml not found")
    return load_ground_truth(GROUND_TRUTH_PATH)


@pytest.fixture(scope="module")
def scan_results():
    """Run a full scan against the sample-repo fixture (no LLM judge)."""
    if not FIXTURE_DIR.exists():
        pytest.skip("sample-repo fixture not found")

    conn = get_connection(":memory:")
    _, findings, report = run_scan(
        str(FIXTURE_DIR),
        conn,
        skip_judge=True,
        output_path="/dev/null",
    )
    conn.close()
    return findings, report


@pytest.fixture(scope="module")
def eval_result(scan_results, ground_truth):
    """Evaluate findings against ground truth."""
    findings, _ = scan_results
    return evaluate(findings, ground_truth)


class TestPrecisionRecall:
    """Evaluate detector accuracy against known ground truth."""

    def test_all_expected_findings_present(self, eval_result):
        """Recall: every expected true positive should be in the results."""
        assert not eval_result.missing, (
            f"Missing {len(eval_result.missing)} expected findings:\n"
            + "\n".join(
                f"  - {m['detector']}: {m.get('file_path', '?')} / {m.get('title', '?')}"
                for m in eval_result.missing
            )
        )

    def test_no_known_false_positives(self, eval_result):
        """Precision: known FP patterns should not appear."""
        assert not eval_result.unexpected_fps, (
            f"Found {len(eval_result.unexpected_fps)} false positives:\n"
            + "\n".join(f"  - {fp}" for fp in eval_result.unexpected_fps)
        )

    def test_precision_at_k(self, eval_result):
        """Precision@k: of all findings, at least 70% should be true positives (ADR-008)."""
        assert eval_result.precision >= 0.70, (
            f"Precision = {eval_result.precision:.0%} "
            f"({eval_result.true_positives}/{eval_result.total_findings} TP), target ≥70%"
        )

    def test_recall(self, eval_result):
        """Recall: at least 90% of expected TPs should be found."""
        assert eval_result.recall >= 0.90, (
            f"Recall = {eval_result.recall:.0%}, target ≥90%"
        )

    def test_report_generated(self, scan_results):
        """The report string should be non-empty and contain findings."""
        _, report = scan_results
        assert "Sentinel Morning Report" in report
        assert "Findings" in report


class TestFalsePositivePrevention:
    """Targeted tests for specific FP-prevention mechanisms."""

    def test_code_block_links_not_flagged(self, scan_results, ground_truth):
        """Links inside fenced code blocks should not be checked."""
        findings, _ = scan_results
        exclude = set(ground_truth.get("exclude_detectors", []))
        filtered = [f for f in findings if f.detector not in exclude]
        code_block_fps = [
            f for f in filtered
            if f.detector == "docs-drift"
            and f.file_path == "README.md"
            and any(s in f.title for s in ["nonexistent", "does_not_exist", "path/to/"])
        ]
        assert code_block_fps == [], (
            f"Found {len(code_block_fps)} code-block FPs: "
            + ", ".join(f.title for f in code_block_fps)
        )

    def test_string_literal_todos_not_flagged(self, scan_results, ground_truth):
        """TODOs inside string literals should be filtered."""
        findings, _ = scan_results
        exclude = set(ground_truth.get("exclude_detectors", []))
        filtered = [f for f in findings if f.detector not in exclude]
        string_fps = [
            f for f in filtered
            if f.detector == "todo-scanner"
            and "fake" in f.title.lower()
        ]
        assert string_fps == [], "String literal TODO was falsely flagged"

    def test_valid_links_not_flagged(self, scan_results, ground_truth):
        """Valid links to existing files should not produce findings."""
        findings, _ = scan_results
        exclude = set(ground_truth.get("exclude_detectors", []))
        filtered = [f for f in findings if f.detector not in exclude]
        readme_fps = [
            f for f in filtered
            if f.detector == "docs-drift"
            and "getting-started" in (f.file_path or "")
            and "README" in f.title
        ]
        assert readme_fps == [], "Valid ../../README.md link was falsely flagged"


class TestPerDetectorBreakdown:
    """Test per-detector precision/recall decomposition."""

    def test_per_detector_results_present(self, eval_result):
        """Eval result should contain per-detector breakdowns."""
        assert eval_result.per_detector, "per_detector should be populated"

    def test_per_detector_covers_expected_detectors(self, eval_result, ground_truth):
        """Every detector that ran and has ground truth should have a breakdown entry."""
        expected_detectors = {e["detector"] for e in ground_truth.get("expected", [])}
        # Only check detectors that appear in per_detector (LLM detectors may not run)
        for det in expected_detectors:
            if det in eval_result.per_detector:
                assert eval_result.per_detector[det].expected > 0

    def test_per_detector_recall_matches_overall(self, eval_result):
        """Sum of per-detector TPs should equal overall TPs."""
        total_tp = sum(d.true_positives for d in eval_result.per_detector.values())
        assert total_tp == eval_result.true_positives

    def test_per_detector_in_to_dict(self, eval_result):
        """per_detector should appear in serialized output."""
        data = eval_result.to_dict()
        assert "per_detector" in data
        assert len(data["per_detector"]) == len(eval_result.per_detector)


class TestFullPipelineEval:
    """Test full-pipeline evaluation with replay provider."""

    @pytest.fixture(scope="class")
    def full_pipeline_results(self, ground_truth):
        """Run full scan with replay provider for judge."""
        if not FIXTURE_DIR.exists():
            pytest.skip("sample-repo fixture not found")

        from sentinel.core.providers.replay import ReplayProvider

        # Use a replay provider that confirms all findings
        replay = ReplayProvider(recordings=[])

        conn = get_connection(":memory:")
        _, findings, report = run_scan(
            str(FIXTURE_DIR),
            conn,
            skip_judge=False,
            provider=replay,
            output_path="/dev/null",
        )
        conn.close()
        return findings, report, replay

    def test_judge_runs_on_all_findings(self, full_pipeline_results):
        """With full pipeline, every finding should have a judge verdict."""
        findings, _, _ = full_pipeline_results
        for f in findings:
            assert f.context is not None, f"Finding {f.title} has no context"
            assert "judge_verdict" in f.context, f"Finding {f.title} missing judge_verdict"

    def test_judge_default_confirms_all(self, full_pipeline_results):
        """Default replay response confirms all findings."""
        findings, _, _ = full_pipeline_results
        for f in findings:
            assert (f.context or {}).get("judge_verdict") == "confirmed", (
                f"Finding {f.title} not confirmed: {(f.context or {}).get('judge_verdict')}"
            )

    def test_tps_survive_judge(self, full_pipeline_results, ground_truth):
        """Expected true positives should still be present after judge."""
        findings, _, _ = full_pipeline_results
        result = evaluate(findings, ground_truth, include_judge_metrics=True)
        assert result.recall >= 0.90, (
            f"Post-judge recall = {result.recall:.0%}, expected ≥90%"
        )

    def test_judge_metrics_computed(self, full_pipeline_results, ground_truth):
        """Judge metrics should be populated in full-pipeline mode."""
        findings, _, _ = full_pipeline_results
        result = evaluate(findings, ground_truth, include_judge_metrics=True)
        assert result.judge is not None
        assert result.judge.total_judged > 0
        assert result.judge.confirmed > 0
        assert result.judge.expected_tp_rejected == 0  # Default replay confirms all

    def test_replay_stats_tracked(self, full_pipeline_results):
        """Replay provider should track hit/miss counts."""
        _, _, replay = full_pipeline_results
        # With empty recordings, all calls should be misses
        assert replay.misses > 0
        assert replay.hits == 0
        assert replay.match_rate == 0.0


class TestReplayProvider:
    """Test ReplayProvider matching and fallback behavior."""

    def test_exact_hash_match(self):
        """Recordings matched by prompt hash should return recorded response."""
        import hashlib

        from sentinel.core.providers.replay import ReplayProvider

        prompt = "test prompt content"
        h = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        recordings = [{"prompt_hash": h, "response": '{"is_real": false}'}]

        replay = ReplayProvider(recordings)
        result = replay.generate(prompt)
        assert result.text == '{"is_real": false}'
        assert replay.hits == 1
        assert replay.misses == 0

    def test_hash_miss_returns_default(self):
        """Unmatched prompts should return the default response."""
        from sentinel.core.providers.replay import ReplayProvider

        replay = ReplayProvider(recordings=[])
        result = replay.generate("any prompt")
        assert "is_real" in result.text
        assert replay.misses == 1

    def test_from_file(self, tmp_path):
        """from_file should load recordings from JSON."""
        import json

        from sentinel.core.providers.replay import ReplayProvider

        recordings_file = tmp_path / "rec.json"
        data = {"recordings": [
            {"prompt_hash": "abc123", "response": '{"test": true}'},
        ]}
        recordings_file.write_text(json.dumps(data))

        replay = ReplayProvider.from_file(recordings_file)
        assert "abc123" in replay._responses

    def test_health_always_true(self):
        """Replay provider should always report healthy."""
        from sentinel.core.providers.replay import ReplayProvider
        assert ReplayProvider(recordings=[]).check_health()

    def test_embed_returns_none(self):
        """Replay provider does not support embeddings."""
        from sentinel.core.providers.replay import ReplayProvider
        assert ReplayProvider(recordings=[]).embed(["text"]) is None


class TestRecordingProvider:
    """Test RecordingProvider wrapping and serialization."""

    def test_records_interactions(self):
        """RecordingProvider should capture prompt hash and response."""
        from sentinel.core.providers.replay import RecordingProvider
        from tests.mock_provider import MockProvider

        inner = MockProvider(generate_text='{"is_real": true}')
        recorder = RecordingProvider(inner)

        recorder.generate("test prompt")

        assert len(recorder.recordings) == 1
        assert recorder.recordings[0]["response"] == '{"is_real": true}'
        assert "prompt_hash" in recorder.recordings[0]

    def test_save_and_reload(self, tmp_path):
        """Saved recordings should be loadable by ReplayProvider."""
        from sentinel.core.providers.replay import RecordingProvider, ReplayProvider
        from tests.mock_provider import MockProvider

        inner = MockProvider(generate_text='{"is_real": true, "adjusted_severity": "low"}')
        recorder = RecordingProvider(inner)

        # Record some interactions
        recorder.generate("first prompt")
        recorder.generate("second prompt")

        # Save
        path = tmp_path / "recordings.json"
        recorder.save(path)

        # Reload
        replay = ReplayProvider.from_file(path)
        assert len(replay._responses) == 2

        # Verify round-trip
        result = replay.generate("first prompt")
        assert "is_real" in result.text
        assert replay.hits == 1

    def test_delegates_to_inner(self):
        """RecordingProvider should pass through calls to the inner provider."""
        from sentinel.core.providers.replay import RecordingProvider
        from tests.mock_provider import MockProvider

        inner = MockProvider(health=True, embed_result=[[1.0, 2.0]])
        recorder = RecordingProvider(inner)

        assert recorder.check_health() is True
        assert recorder.embed(["text"]) == [[1.0, 2.0]]


class TestFindingsFormatGroundTruth:
    """Test that evaluate() supports [[findings]] format with verdict field."""

    def test_findings_tp_treated_as_expected(self):
        """Entries with verdict='tp' in [[findings]] count as expected TPs."""
        from sentinel.models import Finding, Evidence, EvidenceType, Severity

        gt = {
            "findings": [
                {"detector": "complexity", "title": "Complex function: foo", "verdict": "tp"},
                {"detector": "complexity", "title": "Complex function: bar", "verdict": "fp"},
            ],
        }
        findings = [
            Finding(
                detector="complexity",
                category="code-quality",
                severity=Severity.LOW,
                title="Complex function: foo (30 lines)",
                description="Long function",
                file_path="src/foo.py",
                evidence=[Evidence(type=EvidenceType.CODE, content="...", source="src/foo.py:1")],
                confidence=0.9,
            ),
        ]
        result = evaluate(findings, gt)
        assert result.true_positives == 1
        assert len(result.missing) == 0

    def test_findings_fp_treated_as_false_positive_pattern(self):
        """Entries with verdict='fp' in [[findings]] flag unexpected FPs."""
        from sentinel.models import Finding, Evidence, EvidenceType, Severity

        gt = {
            "findings": [
                {"detector": "dead-code", "title": "Unused: helper", "verdict": "fp"},
            ],
        }
        findings = [
            Finding(
                detector="dead-code",
                category="code-quality",
                severity=Severity.LOW,
                title="Unused: helper function",
                description="Unused",
                file_path="src/util.py",
                evidence=[Evidence(type=EvidenceType.CODE, content="...", source="src/util.py:5")],
                confidence=0.8,
            ),
        ]
        result = evaluate(findings, gt)
        assert result.false_positives_found == 1

    def test_mixed_expected_and_findings_formats(self):
        """Both [[expected]] and [[findings]] entries combine correctly."""
        from sentinel.models import Finding, Evidence, EvidenceType, Severity

        gt = {
            "expected": [
                {"detector": "todo-scanner", "title": "TODO"},
            ],
            "findings": [
                {"detector": "complexity", "title": "Complex function: foo", "verdict": "tp"},
            ],
        }
        findings = [
            Finding(
                detector="todo-scanner",
                category="todo-fixme",
                severity=Severity.LOW,
                title="TODO: fix this",
                description="...",
                file_path="src/a.py",
                evidence=[Evidence(type=EvidenceType.CODE, content="...", source="src/a.py:1")],
                confidence=0.9,
            ),
            Finding(
                detector="complexity",
                category="code-quality",
                severity=Severity.LOW,
                title="Complex function: foo (30 lines)",
                description="...",
                file_path="src/b.py",
                evidence=[Evidence(type=EvidenceType.CODE, content="...", source="src/b.py:1")],
                confidence=0.9,
            ),
        ]
        result = evaluate(findings, gt)
        assert result.true_positives == 2
        assert len(result.missing) == 0
