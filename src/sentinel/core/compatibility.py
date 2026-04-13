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
# Updated: 2026-04-13
# Sources: sample-repo, pip-tools, sentinel self-scan
# Models tested: qwen3.5:4b, qwen3.5:9b-q4_K_M, gpt-5.4-nano, gpt-5.4-mini, gpt-5.4

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
     "notes": "Frontier models. Benchmarked on sample-repo (87% precision, 97% recall)"},
]

# Detector metadata for the matrix
DETECTOR_INFO = {
    "lint-runner": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs ruff lint on Python source files",
        "language": "Python",
    },
    "eslint-runner": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs ESLint on JavaScript/TypeScript files",
        "language": "JS/TS",
    },
    "todo-scanner": {
        "tier": "deterministic", "capability": "none",
        "description": "Finds TODO/FIXME/HACK/XXX comments",
        "language": "Any",
    },
    "docs-drift": {
        "tier": "deterministic", "capability": "none",
        "description": "Detects broken links, stale paths, and dependency drift in docs",
        "language": "Any",
    },
    "complexity": {
        "tier": "heuristic", "capability": "none",
        "description": "Flags functions with high cyclomatic complexity or length",
        "language": "Python",
    },
    "dead-code": {
        "tier": "heuristic", "capability": "none",
        "description": "Identifies exported symbols never imported elsewhere",
        "language": "Python",
    },
    "unused-deps": {
        "tier": "deterministic", "capability": "none",
        "description": "Flags declared dependencies not imported in source",
        "language": "Python",
    },
    "stale-env": {
        "tier": "deterministic", "capability": "none",
        "description": "Detects drift between .env docs and actual env var usage",
        "language": "Any",
    },
    "dep-audit": {
        "tier": "deterministic", "capability": "none",
        "description": "Checks for known vulnerabilities via pip-audit/npm audit",
        "language": "Python, JS",
    },
    "git-hotspots": {
        "tier": "heuristic", "capability": "none",
        "description": "Identifies high-churn, fix-heavy files from git history",
        "language": "Any",
    },
    "go-linter": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs go vet and staticcheck on Go modules",
        "language": "Go",
    },
    "rust-clippy": {
        "tier": "deterministic", "capability": "none",
        "description": "Runs cargo clippy on Rust projects",
        "language": "Rust",
    },
    "semantic-drift": {
        "tier": "llm-assisted", "capability": "basic",
        "description": "Compares doc sections against code for semantic consistency",
        "language": "Any",
    },
    "test-coherence": {
        "tier": "llm-assisted", "capability": "basic",
        "description": "Checks whether tests meaningfully validate their implementations",
        "language": "Python",
    },
    "cicd-drift": {
        "tier": "deterministic", "capability": "none",
        "description": "Detects stale path references in GitHub Actions and Dockerfiles",
        "language": "Any",
    },
    "architecture-drift": {
        "tier": "deterministic", "capability": "none",
        "description": "Enforces import-graph layer boundaries from architecture config",
        "language": "Python",
    },
    "inline-comment-drift": {
        "tier": "llm-assisted", "capability": "basic",
        "description": "Detects docstrings that no longer match their function code",
        "language": "Python",
    },
    "intent-comparison": {
        "tier": "llm-assisted", "capability": "advanced",
        "description": "Multi-artifact triangulation: code vs docstring vs tests vs docs",
        "language": "Python",
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
    _e("(judge)", "cloud-small", "advanced", QualityRating.EXCELLENT, "<5%",
       "92% precision on sample-repo (36 findings). Best judge quality tested.",
       "2026-04-13"),
    _e("(judge)", "cloud-frontier", "advanced", QualityRating.GOOD, "~13%",
       "87% precision on sample-repo (38 findings). Confirms more aggressively — "
       "2 extra inline-comment-drift findings vs mini may be marginal.",
       "2026-04-13"),

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
    _e("semantic-drift", "cloud-small", "basic", QualityRating.GOOD, "<15%",
       "Same finding pattern as nano (1 on sample-repo, 4 on pip-tools). Consistent.",
       "2026-04-13"),
    _e("semantic-drift", "cloud-frontier", "basic", QualityRating.GOOD, "<15%",
       "Same finding pattern (1 on sample-repo). Consistent across all model classes.",
       "2026-04-13"),
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
    _e("test-coherence", "cloud-small", "basic", QualityRating.GOOD, "~15%",
       "1 finding on sample-repo (same as nano), 4 on pip-tools. Consistent quality.",
       "2026-04-13"),
    _e("test-coherence", "cloud-frontier", "basic", QualityRating.GOOD, "~15%",
       "1 finding on sample-repo. Consistent with lower model classes.",
       "2026-04-13"),
    _e("test-coherence", "cloud-nano", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode (structured gap analysis) not yet benchmarked"),
    _e("test-coherence", "cloud-small", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode not yet benchmarked"),
    _e("test-coherence", "cloud-frontier", "standard", QualityRating.UNTESTED, "?",
       "Enhanced mode not yet benchmarked"),

    # ── inline-comment-drift (LLM-assisted, basic tier) ──────────
    _e("inline-comment-drift", "4b-local", "basic", QualityRating.UNTESTED, "?",
       "Not yet benchmarked (requires dGPU).",
       "2026-04-13"),
    _e("inline-comment-drift", "9b-local", "basic", QualityRating.UNTESTED, "?",
       "Not yet benchmarked (requires dGPU)."),
    _e("inline-comment-drift", "cloud-nano", "basic", QualityRating.UNTESTED, "?",
       "Not yet benchmarked with full detector set."),
    _e("inline-comment-drift", "cloud-small", "basic", QualityRating.GOOD, "<15%",
       "2 findings on sample-repo (within 92% overall precision), "
       "6 on pip-tools. Finds real docstring-code drift. Very slow (~336s on pip-tools).",
       "2026-04-13"),
    _e("inline-comment-drift", "cloud-frontier", "basic", QualityRating.GOOD, "~15%",
       "4 findings on sample-repo (2 more than mini — possibly marginal). "
       "Overall 87% precision. Quality close to mini.",
       "2026-04-13"),

    # ── intent-comparison (LLM-assisted, advanced tier) ──────────
    _e("intent-comparison", "4b-local", "advanced", QualityRating.UNTESTED, "?",
       "Requires advanced model. Not expected to work well at 4B.",
       "2026-04-13"),
    _e("intent-comparison", "9b-local", "advanced", QualityRating.UNTESTED, "?",
       "Requires advanced model. Not expected to work well at 9B."),
    _e("intent-comparison", "cloud-nano", "advanced", QualityRating.UNTESTED, "?",
       "Not benchmarked with full detector set on nano."),
    _e("intent-comparison", "cloud-small", "advanced", QualityRating.FAIR, "~50% (est)",
       "0 findings on sample-repo (small repo). 35 findings on pip-tools — "
       "very noisy, likely high FP rate. Per-detector precision unknown. "
       "Slow (~75s on pip-tools). Use with caution.",
       "2026-04-13"),
    _e("intent-comparison", "cloud-frontier", "advanced", QualityRating.UNTESTED, "?",
       "0 findings on sample-repo. Not yet benchmarked on larger repo.",
       "2026-04-13"),
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
            "language": det_info.get("language", "Any"),
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


# ── Benchmark-driven prompt strategy (ADR-016) ──────────────────


# Known model name → model class ID mapping.
# Substring matching: if a model name contains the key, it maps to that class.
_MODEL_NAME_TO_CLASS: dict[str, str] = {
    "qwen3.5:4b": "4b-local",
    "qwen3.5:9b": "9b-local",
    "gpt-5.4-nano": "cloud-nano",
    "gpt-5.4-mini": "cloud-small",
    "claude-haiku-4.5": "cloud-small",
    "haiku-4.5": "cloud-small",
    "gpt-5.4": "cloud-frontier",
    "claude-sonnet-4": "cloud-frontier",
    "claude-sonnet-4.6": "cloud-frontier",
}


def model_name_to_class(model: str) -> str | None:
    """Map a model name to a known model class ID.

    Uses substring matching against known model names.
    Returns None if the model is not in the reference data.
    """
    model_lower = model.lower()
    # Check longest keys first to avoid "gpt-5.4" matching before "gpt-5.4-nano"
    for key in sorted(_MODEL_NAME_TO_CLASS, key=len, reverse=True):
        if key in model_lower:
            return _MODEL_NAME_TO_CLASS[key]
    return None


def get_reference_quality(
    model: str, detector: str,
) -> QualityRating | None:
    """Look up the reference benchmark quality for a model+detector pair.

    Returns the QualityRating if the model is in the reference data and
    a rating exists for this detector, or None if unknown.
    """
    model_class = model_name_to_class(model)
    if model_class is None:
        return None

    # Look up using the detector's declared capability tier
    det_info = DETECTOR_INFO.get(detector)
    cap = det_info["capability"] if det_info else "none"
    entry = get_entry(detector, model_class, cap)
    if entry and entry.rating not in (QualityRating.NA, QualityRating.UNTESTED):
        return entry.rating
    return None


def get_enhanced_quality(
    model: str, detector: str,
) -> QualityRating | None:
    """Look up the reference quality for the *enhanced* prompt mode.

    Enhanced mode is benchmarked at the ``standard`` capability tier.
    Returns the QualityRating if an entry exists and has been tested,
    or None if the enhanced mode quality is unknown for this combo.
    """
    model_class = model_name_to_class(model)
    if model_class is None:
        return None

    entry = get_entry(detector, model_class, "standard")
    if entry and entry.rating not in (QualityRating.NA, QualityRating.UNTESTED):
        return entry.rating
    return None


def should_use_enhanced_prompt(
    model: str,
    detector: str,
    model_capability: str = "basic",
) -> bool:
    """Decide whether to use enhanced (structured) prompts for this model+detector.

    Decision priority (ADR-016):
    1. Benchmark data: if enhanced-mode quality is GOOD or better → True
    2. Explicit override: if model_capability is "standard" or "advanced" → True
    3. Default: False (binary prompt — safe for any model)

    Note: The basic-tier quality rating (how well the model does with binary
    prompts) is NOT used here. We specifically check the standard-tier
    entry, which measures enhanced-mode performance.
    """
    # 1. Check reference benchmark data for enhanced mode
    quality = get_enhanced_quality(model, detector)
    if quality is not None:
        return quality in (QualityRating.EXCELLENT, QualityRating.GOOD)

    # 2. Fall back to explicit model_capability config hint
    return model_capability in ("standard", "advanced")
