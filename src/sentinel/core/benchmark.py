"""Benchmarking module — run detectors with timing and model comparison.

Produces structured per-detector stats for comparing models and tracking
detector performance over time.
"""

from __future__ import annotations

import logging
import time
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sentinel.core.eval import evaluate, load_ground_truth
from sentinel.detectors.base import Detector, get_all_detectors
from sentinel.models import DetectorContext, Finding, ScopeType

logger = logging.getLogger(__name__)


@dataclass
class DetectorBenchmark:
    """Stats for a single detector in a benchmark run."""

    name: str
    finding_count: int
    duration_ms: float
    categories: list[str]
    tier: str


@dataclass
class BenchmarkResult:
    """Results of a full benchmark run."""

    repo_path: str
    timestamp: str
    model: str
    provider: str
    model_capability: str
    total_findings: int
    total_duration_ms: float
    detector_count: int
    detectors: list[DetectorBenchmark]
    eval_result: dict[str, Any] | None = None  # If ground truth was available

    def to_toml_str(self) -> str:
        """Serialize to a human-readable TOML string."""
        lines = [
            "# Sentinel Benchmark Results",
            f"# Generated: {self.timestamp}",
            "",
            "[benchmark]",
            f'repo_path = "{self.repo_path}"',
            f'timestamp = "{self.timestamp}"',
            f'model = "{self.model}"',
            f'provider = "{self.provider}"',
            f'model_capability = "{self.model_capability}"',
            f"total_findings = {self.total_findings}",
            f"total_duration_ms = {self.total_duration_ms:.1f}",
            f"detector_count = {self.detector_count}",
            "",
        ]

        if self.eval_result:
            lines.append("[benchmark.eval]")
            for key, value in self.eval_result.items():
                if isinstance(value, float):
                    lines.append(f"{key} = {value:.4f}")
                elif isinstance(value, list):
                    lines.append(f"{key} = {len(value)}")
                else:
                    lines.append(f"{key} = {value}")
            lines.append("")

        for det in sorted(self.detectors, key=lambda d: -d.finding_count):
            lines.append("[[benchmark.detectors]]")
            lines.append(f'name = "{det.name}"')
            lines.append(f"finding_count = {det.finding_count}")
            lines.append(f"duration_ms = {det.duration_ms:.1f}")
            lines.append(f'tier = "{det.tier}"')
            cats = ", ".join(f'"{c}"' for c in det.categories)
            lines.append(f"categories = [{cats}]")
            lines.append("")

        return "\n".join(lines)


def run_benchmark(
    repo_path: str,
    *,
    provider: Any | None = None,
    skip_judge: bool = False,
    model: str = "unknown",
    provider_name: str = "unknown",
    model_capability: str = "basic",
    num_ctx: int = 2048,
    detectors: list[Detector] | None = None,
    enabled_detectors: list[str] | None = None,
    disabled_detectors: list[str] | None = None,
    detectors_dir: str = "",
    ground_truth_path: str | None = None,
) -> BenchmarkResult:
    """Run all detectors with timing, producing benchmark stats.

    Unlike run_scan, this does NOT use the full pipeline (no dedup,
    no persistence, no report). It focuses on raw detector output
    and timing for comparison purposes.
    """
    repo_root = str(Path(repo_path).resolve())
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build context
    ctx = DetectorContext(
        repo_root=repo_root,
        scope=ScopeType.FULL,
        config={
            "provider": provider,
            "skip_llm": skip_judge or provider is None,
            "num_ctx": num_ctx,
            "model_capability": model_capability,
        },
    )

    # Load detectors
    if detectors is None:
        from sentinel.core.runner import _ensure_detectors_loaded
        _ensure_detectors_loaded()
        from sentinel.detectors.base import load_entrypoint_detectors
        load_entrypoint_detectors()
        if detectors_dir:
            from sentinel.detectors.base import load_custom_detectors
            load_custom_detectors(detectors_dir)
        detectors = get_all_detectors()

    # Filter
    if enabled_detectors:
        detectors = [d for d in detectors if d.name in enabled_detectors]
    elif disabled_detectors:
        skip_set = set(disabled_detectors)
        detectors = [d for d in detectors if d.name not in skip_set]

    # Run with timing
    detector_results: list[DetectorBenchmark] = []
    all_findings: list[Finding] = []
    total_start = time.monotonic()

    for det in detectors:
        start = time.monotonic()
        try:
            findings = det.detect(ctx)
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                "  %s: %d findings in %.0fms", det.name, len(findings), elapsed,
            )
            all_findings.extend(findings)
            detector_results.append(DetectorBenchmark(
                name=det.name,
                finding_count=len(findings),
                duration_ms=round(elapsed, 1),
                categories=det.categories,
                tier=det.tier.value,
            ))
        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("Detector %s failed (%.0fms)", det.name, elapsed)
            detector_results.append(DetectorBenchmark(
                name=det.name,
                finding_count=-1,  # Signals failure
                duration_ms=round(elapsed, 1),
                categories=det.categories,
                tier=det.tier.value,
            ))

    total_elapsed = (time.monotonic() - total_start) * 1000

    # Evaluate against ground truth if available
    eval_dict: dict[str, Any] | None = None
    if ground_truth_path:
        gt_path = Path(ground_truth_path)
        if gt_path.exists():
            gt = load_ground_truth(gt_path)
            result = evaluate(all_findings, gt)
            eval_dict = result.to_dict()
        else:
            logger.warning("Ground truth not found: %s", gt_path)

    return BenchmarkResult(
        repo_path=repo_root,
        timestamp=timestamp,
        model=model,
        provider=provider_name,
        model_capability=model_capability,
        total_findings=len(all_findings),
        total_duration_ms=round(total_elapsed, 1),
        detector_count=len(detectors),
        detectors=detector_results,
        eval_result=eval_dict,
    )


def save_benchmark(result: BenchmarkResult, output_dir: str) -> str:
    """Save benchmark results to a TOML file.

    Returns the path to the saved file.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Repo name for the filename
    repo_name = Path(result.repo_path).name
    model_safe = result.model.replace("/", "-").replace(":", "-")
    ts = result.timestamp.replace(":", "").replace("-", "")[:15]
    filename = f"{ts}-{repo_name}-{model_safe}.toml"

    file_path = out_path / filename
    file_path.write_text(result.to_toml_str(), encoding="utf-8")
    return str(file_path)


def load_benchmark(path: str | Path) -> dict[str, Any]:
    """Load a benchmark TOML file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def compare_benchmarks(paths: list[str | Path]) -> str:
    """Compare multiple benchmark results and produce a summary table.

    Returns a markdown-formatted comparison.
    """
    results = [load_benchmark(p) for p in paths]
    if not results:
        return "No benchmark results to compare."

    lines = [
        "# Benchmark Comparison",
        "",
        "| Metric | " + " | ".join(
            r["benchmark"]["model"] for r in results
        ) + " |",
        "|--------|" + "|".join("--------|" for _ in results),
        "| Provider | " + " | ".join(
            r["benchmark"]["provider"] for r in results
        ) + " |",
        "| Total findings | " + " | ".join(
            str(r["benchmark"]["total_findings"]) for r in results
        ) + " |",
        "| Total time (ms) | " + " | ".join(
            f'{r["benchmark"]["total_duration_ms"]:.0f}' for r in results
        ) + " |",
        "| Detectors run | " + " | ".join(
            str(r["benchmark"]["detector_count"]) for r in results
        ) + " |",
    ]

    # Add eval metrics if available
    has_eval = any("eval" in r.get("benchmark", {}) for r in results)
    if has_eval:
        lines.append("| **Precision** | " + " | ".join(
            f'{r["benchmark"].get("eval", {}).get("precision", "—"):.2%}'
            if isinstance(r["benchmark"].get("eval", {}).get("precision"), (int, float))
            else "—"
            for r in results
        ) + " |")
        lines.append("| **Recall** | " + " | ".join(
            f'{r["benchmark"].get("eval", {}).get("recall", "—"):.2%}'
            if isinstance(r["benchmark"].get("eval", {}).get("recall"), (int, float))
            else "—"
            for r in results
        ) + " |")

    lines.extend(["", "## Per-Detector Breakdown", ""])

    # Collect all detector names
    all_dets: set[str] = set()
    for r in results:
        for d in r["benchmark"].get("detectors", []):
            all_dets.add(d["name"])

    lines.append("| Detector | " + " | ".join(
        r["benchmark"]["model"] for r in results
    ) + " |")
    lines.append("|----------|" + "|".join("--------|" for _ in results))

    for det_name in sorted(all_dets):
        row = f"| {det_name} | "
        for r in results:
            det_data = next(
                (d for d in r["benchmark"].get("detectors", []) if d["name"] == det_name),
                None,
            )
            if det_data:
                count = det_data["finding_count"]
                ms = det_data["duration_ms"]
                row += f"{count} ({ms:.0f}ms) | "
            else:
                row += "— | "
        lines.append(row)

    return "\n".join(lines)
