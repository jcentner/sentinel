"""Model-detector compatibility matrix — empirical quality ratings.

This module defines the known compatibility between model classes and
detectors at each capability tier. Ratings are based on real-world
benchmarks (see docs/reference/model-benchmarks.md).

The matrix is the authoritative source for:
- The CLI ``sentinel compatibility`` command
- The web UI's compatibility matrix page
- The docs/reference/compatibility-matrix.md documentation
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class QualityRating(str, enum.Enum):
    """Empirical quality rating for a model-detector combination.

    Based on false-positive rate and finding accuracy from benchmarks.
    """

    EXCELLENT = "excellent"  # <10% FP, high signal — recommended
    GOOD = "good"  # 10-25% FP, reliable for triage
    FAIR = "fair"  # 25-40% FP, usable but noisy — human review essential
    POOR = "poor"  # >40% FP, not recommended — consider a better model
    NA = "n/a"  # Detector doesn't use a model at this tier
    UNTESTED = "untested"  # No benchmark data yet


@dataclass(frozen=True)
class CompatibilityEntry:
    """Single cell in the model-detector matrix."""

    detector: str
    model_class: str  # "4B local", "9B local", "cloud-nano", "cloud-frontier"
    capability_tier: str  # "none", "basic", "standard"
    rating: QualityRating
    fp_rate: str  # e.g., "<10%", "~40%", "n/a"
    notes: str  # Brief explanation
    benchmark_date: str  # When this was measured


# ── Empirical compatibility data ─────────────────────────────────
#
# Updated: 2026-04-11
# Sources: Self-scan, tsgbuilder, wyoclear, sample-repo fixture
# Models tested: qwen3.5:4b, qwen3.5:9b-q4_K_M, gpt-5.4-nano

# Model class definitions for display
#
# These represent empirically-tested model classes, not assumed equivalences.
# Rankings based on aggregate benchmarks (independent scores: 4B≈27, 9B≈32,
# gpt-5.4-nano≈38-44, Haiku 4.5≈31-37, gpt-5.4-mini≈38-49).
MODEL_CLASSES = [
    {"id": "4b-local", "name": "4B Local", "example": "qwen3.5:4b",
     "vram": "~3.4 GB", "speed": "~53 tok/s",
     "tier": "basic",
     "notes": "Best value for deterministic detectors + judge + semantic-drift"},
    {"id": "9b-local", "name": "9B Local", "example": "qwen3.5:9b-q4_K_M",
     "vram": "~6.6 GB", "speed": "~19 tok/s",
     "tier": "basic",
     "notes": "Marginal improvement over 4B at 2-3× slower. Not recommended on 8 GB VRAM"},
    {"id": "cloud-nano", "name": "Cloud Nano", "example": "gpt-5.4-nano",
     "vram": "n/a", "speed": "~100 tok/s",
     "tier": "standard",
     "notes": "Substantially stronger than local models. Best for test-coherence"},
    {"id": "cloud-small", "name": "Cloud Small", "example": "gpt-5.4-mini, Claude Haiku 4.5",
     "vram": "n/a", "speed": "varies",
     "tier": "advanced",
     "notes": "Near-frontier. GPT-5.4-mini and Haiku 4.5 are similar tier, not identical"},
    {"id": "cloud-frontier", "name": "Cloud Frontier", "example": "gpt-5.4, Claude Sonnet 4.6",
     "vram": "n/a", "speed": "varies",
     "tier": "advanced",
     "notes": "Frontier models. Not yet benchmarked for Sentinel"},
]

# Detector metadata for the matrix
DETECTOR_INFO = {
    "lint-runner": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs ruff lint on Python source files",
    },
    "eslint-runner": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs ESLint on JavaScript/TypeScript files",
    },
    "todo-scanner": {
        "tier": "deterministic", "capability": "none",
        "description": "Finds TODO/FIXME/HACK/XXX comments",
    },
    "docs-drift": {
        "tier": "deterministic", "capability": "none",
        "description": "Detects broken links, stale paths, and dependency drift in docs",
    },
    "complexity": {
        "tier": "heuristic", "capability": "none",
        "description": "Flags functions with high cyclomatic complexity or length",
    },
    "dead-code": {
        "tier": "heuristic", "capability": "none",
        "description": "Identifies exported symbols never imported elsewhere",
    },
    "unused-deps": {
        "tier": "deterministic", "capability": "none",
        "description": "Flags declared dependencies not imported in source",
    },
    "stale-env": {
        "tier": "deterministic", "capability": "none",
        "description": "Detects drift between .env docs and actual env var usage",
    },
    "dep-audit": {
        "tier": "deterministic", "capability": "none",
        "description": "Checks for known vulnerabilities via pip-audit/npm audit",
    },
    "git-hotspots": {
        "tier": "heuristic", "capability": "none",
        "description": "Identifies high-churn, fix-heavy files from git history",
    },
    "go-linter": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs go vet and staticcheck on Go modules",
    },
    "rust-clippy": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs cargo clippy on Rust projects",
    },
    "semantic-drift": {
        "tier": "llm-assisted", "capability": "basic",
        "description": "Compares doc sections against code for semantic consistency",
    },
    "test-coherence": {
        "tier": "llm-assisted", "capability": "basic",
        "description": "Checks whether tests meaningfully validate their implementations",
    },
}


def _e(
    detector: str, model_class: str, tier: str,
    rating: QualityRating, fp_rate: str, notes: str,
    date: str = "2026-04-11",
) -> CompatibilityEntry:
    return CompatibilityEntry(
        detector=detector, model_class=model_class,
        capability_tier=tier, rating=rating,
        fp_rate=fp_rate, notes=notes, benchmark_date=date,
    )


# The full matrix.  Deterministic detectors get EXCELLENT/n/a
# because the model only affects judging, not detection.
COMPATIBILITY_MATRIX: list[CompatibilityEntry] = [
    # ── Deterministic detectors (model only used for judge) ──────
    # Judge quality is the only model-dependent axis for these.
    # All models can confirm/reject findings; 4B is acceptably accurate.
    *[_e(det, mc, "none", QualityRating.NA, "n/a",
         f"{'Deterministic' if DETECTOR_INFO[det]['tier'] == 'deterministic' else 'Heuristic'}"
         " detector — model not used for detection")
      for det in DETECTOR_INFO if DETECTOR_INFO[det]["capability"] == "none"
      for mc in ["4b-local", "9b-local", "cloud-nano", "cloud-small", "cloud-frontier"]],

    # ── Judge quality per model class ────────────────────────────
    # These rate how well the model performs as a *judge* of findings
    # from deterministic detectors.
    _e("(judge)", "4b-local", "basic", QualityRating.GOOD, "~15%",
       "Confirms most TPs correctly. Occasionally rejects valid complexity findings.",
       "2026-04-11"),
    _e("(judge)", "9b-local", "basic", QualityRating.FAIR, "~10%",
       "More skeptical — rejects 58% of findings. Over-filters real issues.",
       "2026-04-06"),
    _e("(judge)", "cloud-nano", "standard", QualityRating.GOOD, "~10%",
       "Selective and fast. Good balance of confirmation and filtering.",
       "2026-04-11"),
    _e("(judge)", "cloud-small", "advanced", QualityRating.UNTESTED, "?",
       "Not yet benchmarked as judge"),
    _e("(judge)", "cloud-frontier", "advanced", QualityRating.UNTESTED, "?",
       "Not yet benchmarked as judge"),

    # ── semantic-drift (LLM-assisted, basic tier) ────────────────
    _e("semantic-drift", "4b-local", "basic", QualityRating.GOOD, "<15%",
       "Binary signal is robust even for small models. Finds real doc-code drift.",
       "2026-04-11"),
    _e("semantic-drift", "9b-local", "basic", QualityRating.GOOD, "<15%",
       "Same quality as 4B but 2-3× slower on 8 GB VRAM. No advantage.",
       "2026-04-11"),
    _e("semantic-drift", "cloud-nano", "basic", QualityRating.EXCELLENT, "<10%",
       "Fastest and most precise. Finds the same issues with fewer false signals.",
       "2026-04-11"),
    _e("semantic-drift", "cloud-nano", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode (structured explanations) not yet benchmarked with cloud-nano"),
    _e("semantic-drift", "cloud-small", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode not yet benchmarked"),
    _e("semantic-drift", "cloud-frontier", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode not yet benchmarked"),

    # ── test-coherence (LLM-assisted, basic tier) ────────────────
    _e("test-coherence", "4b-local", "basic", QualityRating.POOR, "~40%",
       "High FP rate: flags CLI tests, mock-based tests, and simple serialization tests "
       "as stale. Not recommended — use a stronger model or skip this detector.",
       "2026-04-11"),
    _e("test-coherence", "9b-local", "basic", QualityRating.FAIR, "~30%",
       "Somewhat better than 4B but still noisy. Marginal improvement does not justify "
       "2-3× slower speed on 8 GB VRAM.",
       "2026-04-11"),
    _e("test-coherence", "cloud-nano", "basic", QualityRating.GOOD, "~15%",
       "Significantly more precise. Correctly handles CLI runners, mocks, and simple tests. "
       "Minimum recommended model for this detector.",
       "2026-04-11"),
    _e("test-coherence", "cloud-nano", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode (structured gap analysis) not yet benchmarked"),
    _e("test-coherence", "cloud-small", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode not yet benchmarked"),
    _e("test-coherence", "cloud-frontier", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode not yet benchmarked"),
]


# ── Query helpers ────────────────────────────────────────────────


def get_matrix_for_detector(detector: str) -> list[CompatibilityEntry]:
    """All compatibility entries for a given detector."""
    return [e for e in COMPATIBILITY_MATRIX if e.detector == detector]


def get_matrix_for_model(model_class: str) -> list[CompatibilityEntry]:
    """All compatibility entries for a given model class."""
    return [e for e in COMPATIBILITY_MATRIX if e.model_class == model_class]


def get_entry(detector: str, model_class: str, tier: str) -> CompatibilityEntry | None:
    """Look up a specific matrix cell."""
    for e in COMPATIBILITY_MATRIX:
        if e.detector == detector and e.model_class == model_class and e.capability_tier == tier:
            return e
    return None


def get_detector_recommendation(detector: str) -> str:
    """Return a brief recommendation for which model to use with a detector."""
    entries = get_matrix_for_detector(detector)
    if not entries:
        return "No benchmark data available."

    # Find best rated entry
    priority = {
        QualityRating.EXCELLENT: 0,
        QualityRating.GOOD: 1,
        QualityRating.FAIR: 2,
        QualityRating.POOR: 3,
        QualityRating.UNTESTED: 4,
        QualityRating.NA: 5,
    }
    rated = [e for e in entries if e.rating not in (QualityRating.NA, QualityRating.UNTESTED)]
    if not rated:
        return "Deterministic detector — no model needed for detection."

    best = min(rated, key=lambda e: priority[e.rating])
    model_info = next((m for m in MODEL_CLASSES if m["id"] == best.model_class), None)
    model_name = model_info["example"] if model_info else best.model_class
    return f"Recommended: {model_name} ({best.rating.value}, FP rate {best.fp_rate})"


def build_summary_table() -> list[dict[str, object]]:
    """Build a summary table: one row per detector, columns per model class.

    Returns list of dicts with keys: detector, tier, capability,
    plus one key per model class id containing {rating, fp_rate, notes}.
    """
    rows = []
    for det_name, det_info in DETECTOR_INFO.items():
        row: dict[str, object] = {
            "detector": det_name,
            "tier": det_info["tier"],
            "capability": det_info["capability"],
            "description": det_info["description"],
        }
        for mc in MODEL_CLASSES:
            entry = get_entry(det_name, mc["id"], det_info["capability"])
            if entry:
                row[mc["id"]] = {
                    "rating": entry.rating.value,
                    "fp_rate": entry.fp_rate,
                    "notes": entry.notes,
                }
            else:
                row[mc["id"]] = {
                    "rating": "untested",
                    "fp_rate": "?",
                    "notes": "Not yet benchmarked",
                }
        rows.append(row)

    # Add judge row
    judge_row: dict[str, object] = {
        "detector": "(judge)",
        "tier": "llm",
        "capability": "basic",
        "description": "LLM judge that evaluates all findings for validity",
    }
    for mc in MODEL_CLASSES:
        # Judge entries exist at various tiers per model class
        entry = None
        for tier in ("basic", "standard", "advanced"):
            entry = get_entry("(judge)", mc["id"], tier)
            if entry:
                break
        if entry:
            judge_row[mc["id"]] = {
                "rating": entry.rating.value,
                "fp_rate": entry.fp_rate,
                "notes": entry.notes,
            }
        else:
            judge_row[mc["id"]] = {
                "rating": "untested",
                "fp_rate": "?",
                "notes": "Not yet benchmarked",
            }
    rows.append(judge_row)

    return rows
