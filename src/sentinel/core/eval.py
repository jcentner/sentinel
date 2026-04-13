"""Evaluation framework — measure precision/recall against ground truth."""

from __future__ import annotations

import logging
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sentinel.models import Finding

logger = logging.getLogger(__name__)


@dataclass
class DetectorEvalResult:
    """Per-detector precision/recall breakdown."""

    detector: str
    total_findings: int
    true_positives: int
    expected: int

    @property
    def precision(self) -> float:
        return self.true_positives / self.total_findings if self.total_findings else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.expected if self.expected else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "total_findings": self.total_findings,
            "true_positives": self.true_positives,
            "expected": self.expected,
            "precision": self.precision,
            "recall": self.recall,
        }


@dataclass
class JudgeEvalResult:
    """Metrics specific to the LLM judge evaluation."""

    total_judged: int = 0
    confirmed: int = 0
    rejected: int = 0
    inconclusive: int = 0
    expected_tp_rejected: int = 0  # Ground-truth TPs the judge wrongly rejected

    @property
    def confirmation_rate(self) -> float:
        return self.confirmed / self.total_judged if self.total_judged else 0.0

    @property
    def rejection_rate(self) -> float:
        return self.rejected / self.total_judged if self.total_judged else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_judged": self.total_judged,
            "confirmed": self.confirmed,
            "rejected": self.rejected,
            "inconclusive": self.inconclusive,
            "expected_tp_rejected": self.expected_tp_rejected,
            "confirmation_rate": self.confirmation_rate,
            "rejection_rate": self.rejection_rate,
        }


@dataclass
class EvalResult:
    """Results of a precision/recall evaluation."""

    total_findings: int
    true_positives: int
    false_positives_found: int
    missing: list[dict[str, str]]  # Expected TPs not found
    unexpected_fps: list[str]  # Known FP patterns that appeared
    per_detector: dict[str, DetectorEvalResult] = field(default_factory=dict)
    judge: JudgeEvalResult | None = None

    @property
    def precision(self) -> float:
        return self.true_positives / self.total_findings if self.total_findings else 0.0

    @property
    def recall(self) -> float:
        expected = self.true_positives + len(self.missing)
        return self.true_positives / expected if expected else 0.0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "total_findings": self.total_findings,
            "true_positives": self.true_positives,
            "false_positives_found": self.false_positives_found,
            "missing": self.missing,
            "unexpected_fps": self.unexpected_fps,
            "precision": self.precision,
            "recall": self.recall,
        }
        if self.per_detector:
            result["per_detector"] = {
                k: v.to_dict() for k, v in sorted(self.per_detector.items())
            }
        if self.judge is not None:
            result["judge"] = self.judge.to_dict()
        return result


def load_ground_truth(path: Path) -> dict[str, Any]:
    """Load a TOML ground truth file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def evaluate(
    findings: list[Finding],
    ground_truth: dict[str, Any],
    *,
    include_judge_metrics: bool = False,
) -> EvalResult:
    """Evaluate findings against a ground truth manifest.

    The ground truth should have:
      expected: list of {detector, file_path, title} — substring matches
      false_positives: list of {detector, file_path, title} — should NOT appear
      exclude_detectors: list of detector names to exclude from evaluation

    When *include_judge_metrics* is True, computes judge-specific metrics
    (confirmation rate, rejection rate, wrongly-rejected TPs).
    """
    exclude = set(ground_truth.get("exclude_detectors", []))
    filtered = [f for f in findings if f.detector not in exclude]

    # Determine which detectors actually ran (produced findings)
    ran_detectors = {f.detector for f in filtered}

    expected = ground_truth.get("expected", [])

    # Also support [[findings]] format: entries with verdict="tp" become expected
    for entry in ground_truth.get("findings", []):
        if entry.get("verdict") == "tp":
            expected.append({
                "detector": entry["detector"],
                "file_path": entry.get("file_path", ""),
                "title": entry.get("title", ""),
            })

    fp_patterns = ground_truth.get("false_positives", [])
    # Also support [[findings]] with verdict="fp" as known false positive patterns
    for entry in ground_truth.get("findings", []):
        if entry.get("verdict") == "fp":
            fp_patterns.append({
                "detector": entry["detector"],
                "file_path": entry.get("file_path", ""),
                "title": entry.get("title", ""),
            })

    # Only evaluate expected entries from detectors that actually ran
    # (avoids penalizing recall when LLM detectors are skipped)
    active_expected = [
        e for e in expected
        if e["detector"] not in exclude and e["detector"] in ran_detectors
    ]

    # Count true positives
    tp_count = 0
    missing: list[dict[str, str]] = []
    for entry in active_expected:
        matched = any(_match(f, entry) for f in filtered)
        if matched:
            tp_count += 1
        else:
            missing.append(entry)

    # Check for known false positive patterns
    unexpected_fps: list[str] = []
    for entry in fp_patterns:
        for f in filtered:
            if _match(f, entry):
                unexpected_fps.append(f"[{f.detector}] {f.title} at {f.file_path}")
                break

    # Per-detector breakdown
    per_detector = _compute_per_detector(filtered, active_expected)

    # Judge metrics (only meaningful when judge has run)
    judge_result = None
    if include_judge_metrics:
        judge_result = _compute_judge_metrics(filtered, active_expected)

    return EvalResult(
        total_findings=len(filtered),
        true_positives=tp_count,
        false_positives_found=len(unexpected_fps),
        missing=missing,
        unexpected_fps=unexpected_fps,
        per_detector=per_detector,
        judge=judge_result,
    )


def _match(finding: Finding, entry: dict[str, str]) -> bool:
    """Check if a finding matches a ground truth entry (fuzzy substring match)."""
    if finding.detector != entry["detector"]:
        return False
    if entry.get("file_path") and entry["file_path"] not in (finding.file_path or ""):
        return False
    if entry.get("title"):
        return entry["title"].lower() in finding.title.lower()
    return True


def _compute_per_detector(
    findings: list[Finding],
    expected: list[dict[str, str]],
) -> dict[str, DetectorEvalResult]:
    """Compute precision/recall per detector."""
    # Group findings by detector
    findings_by_det: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        findings_by_det[f.detector].append(f)

    # Group expected entries by detector
    expected_by_det: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in expected:
        expected_by_det[entry["detector"]].append(entry)

    # Combine all detector names
    all_detectors = set(findings_by_det.keys()) | set(expected_by_det.keys())

    result: dict[str, DetectorEvalResult] = {}
    for det in sorted(all_detectors):
        det_findings = findings_by_det.get(det, [])
        det_expected = expected_by_det.get(det, [])

        tp = 0
        for entry in det_expected:
            if any(_match(f, entry) for f in det_findings):
                tp += 1

        result[det] = DetectorEvalResult(
            detector=det,
            total_findings=len(det_findings),
            true_positives=tp,
            expected=len(det_expected),
        )

    return result


def _compute_judge_metrics(
    findings: list[Finding],
    expected: list[dict[str, str]],
) -> JudgeEvalResult:
    """Compute LLM judge-specific metrics from judged findings."""
    total = 0
    confirmed = 0
    rejected = 0
    inconclusive = 0
    tp_rejected = 0

    for f in findings:
        verdict = (f.context or {}).get("judge_verdict")
        if verdict is None:
            continue  # Judge didn't run on this finding
        total += 1
        if verdict == "confirmed":
            confirmed += 1
        elif verdict == "likely_false_positive":
            rejected += 1
            # Check if this was a ground-truth TP that the judge wrongly rejected
            if any(_match(f, entry) for entry in expected):
                tp_rejected += 1
        else:
            inconclusive += 1

    return JudgeEvalResult(
        total_judged=total,
        confirmed=confirmed,
        rejected=rejected,
        inconclusive=inconclusive,
        expected_tp_rejected=tp_rejected,
    )
