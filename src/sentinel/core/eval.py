"""Evaluation framework — measure precision/recall against ground truth."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sentinel.models import Finding

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Results of a precision/recall evaluation."""

    total_findings: int
    true_positives: int
    false_positives_found: int
    missing: list[dict[str, str]]  # Expected TPs not found
    unexpected_fps: list[str]  # Known FP patterns that appeared

    @property
    def precision(self) -> float:
        return self.true_positives / self.total_findings if self.total_findings else 0.0

    @property
    def recall(self) -> float:
        expected = self.true_positives + len(self.missing)
        return self.true_positives / expected if expected else 0.0


def load_ground_truth(path: Path) -> dict[str, Any]:
    """Load a TOML ground truth file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def evaluate(
    findings: list[Finding],
    ground_truth: dict[str, Any],
) -> EvalResult:
    """Evaluate findings against a ground truth manifest.

    The ground truth should have:
      expected: list of {detector, file_path, title} — substring matches
      false_positives: list of {detector, file_path, title} — should NOT appear
      exclude_detectors: list of detector names to exclude from evaluation
    """
    exclude = set(ground_truth.get("exclude_detectors", []))
    filtered = [f for f in findings if f.detector not in exclude]

    expected = ground_truth.get("expected", [])
    fp_patterns = ground_truth.get("false_positives", [])

    # Count true positives
    tp_count = 0
    missing: list[dict[str, str]] = []
    for entry in expected:
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

    return EvalResult(
        total_findings=len(filtered),
        true_positives=tp_count,
        false_positives_found=len(unexpected_fps),
        missing=missing,
        unexpected_fps=unexpected_fps,
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
