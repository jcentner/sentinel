"""Tests for finding clustering logic."""

from __future__ import annotations

from sentinel.core.clustering import (
    FindingCluster,
    _normalize_title,
    cluster_by_pattern,
    cluster_findings,
)
from sentinel.core.report import generate_report
from sentinel.models import (
    Evidence,
    EvidenceType,
    Finding,
    RunSummary,
    ScopeType,
    Severity,
)


def _f(file_path: str = "src/x.py", **kwargs) -> Finding:
    defaults = {
        "detector": "test",
        "category": "code-quality",
        "severity": Severity.MEDIUM,
        "confidence": 0.8,
        "title": f"Issue in {file_path}",
        "description": "Something wrong",
        "evidence": [Evidence(type=EvidenceType.CODE, source=file_path, content="bad")],
        "file_path": file_path,
        "line_start": 10,
    }
    defaults.update(kwargs)
    return Finding(**defaults)


def _make_run() -> RunSummary:
    return RunSummary(id=1, repo_path="/tmp/test-repo", scope=ScopeType.FULL)


class TestClusterFindings:
    """Unit tests for the cluster_findings function."""

    def test_empty_list(self):
        assert cluster_findings([]) == []

    def test_single_finding_stays_standalone(self):
        f = _f()
        result = cluster_findings([f])
        assert result == [f]

    def test_below_threshold_stays_standalone(self):
        """Two findings in the same dir don't cluster (min_size=3)."""
        items = [_f("src/a.py"), _f("src/b.py")]
        result = cluster_findings(items)
        assert len(result) == 2
        assert all(isinstance(r, Finding) for r in result)

    def test_three_findings_same_dir_form_cluster(self):
        items = [_f("src/a.py"), _f("src/b.py"), _f("src/c.py")]
        result = cluster_findings(items)
        assert len(result) == 1
        assert isinstance(result[0], FindingCluster)
        assert len(result[0].findings) == 3
        assert result[0].common_path == "src"

    def test_different_dirs_stay_standalone(self):
        items = [_f("src/a.py"), _f("lib/b.py"), _f("tests/c.py")]
        result = cluster_findings(items)
        assert len(result) == 3
        assert all(isinstance(r, Finding) for r in result)

    def test_mixed_cluster_and_standalone(self):
        items = [
            _f("src/a.py"),
            _f("src/b.py"),
            _f("src/c.py"),
            _f("lib/d.py"),
        ]
        result = cluster_findings(items)
        clusters = [r for r in result if isinstance(r, FindingCluster)]
        standalone = [r for r in result if isinstance(r, Finding)]
        assert len(clusters) == 1
        assert len(standalone) == 1
        assert clusters[0].common_path == "src"

    def test_multiple_clusters(self):
        items = [
            _f("src/a.py"),
            _f("src/b.py"),
            _f("src/c.py"),
            _f("lib/x.py"),
            _f("lib/y.py"),
            _f("lib/z.py"),
        ]
        result = cluster_findings(items)
        clusters = [r for r in result if isinstance(r, FindingCluster)]
        assert len(clusters) == 2
        paths = {c.common_path for c in clusters}
        assert paths == {"src", "lib"}

    def test_largest_cluster_first(self):
        items = [
            _f("lib/x.py"),
            _f("lib/y.py"),
            _f("lib/z.py"),
            _f("src/a.py"),
            _f("src/b.py"),
            _f("src/c.py"),
            _f("src/d.py"),
        ]
        result = cluster_findings(items)
        clusters = [r for r in result if isinstance(r, FindingCluster)]
        assert len(clusters) == 2
        # src has 4 findings, lib has 3 — src cluster should come first
        assert clusters[0].common_path == "src"
        assert clusters[1].common_path == "lib"

    def test_custom_min_size(self):
        items = [_f("src/a.py"), _f("src/b.py")]
        result = cluster_findings(items, min_size=2)
        assert len(result) == 1
        assert isinstance(result[0], FindingCluster)

    def test_min_size_one_returns_all_standalone(self):
        """min_size < 2 disables clustering."""
        items = [_f("src/a.py"), _f("src/b.py"), _f("src/c.py")]
        result = cluster_findings(items, min_size=1)
        assert all(isinstance(r, Finding) for r in result)

    def test_no_file_path_findings_cluster(self):
        """Findings without file_path are grouped under empty string."""
        items = [_f(file_path=None), _f(file_path=None), _f(file_path=None)]
        # file_path=None should group together
        result = cluster_findings(items)
        assert len(result) == 1
        assert isinstance(result[0], FindingCluster)
        assert result[0].common_path == ""

    def test_cluster_label(self):
        items = [_f("src/a.py"), _f("src/b.py"), _f("src/c.py")]
        result = cluster_findings(items)
        cluster = result[0]
        assert "3 findings" in cluster.label
        assert "src" in cluster.label

    def test_nested_dirs_cluster_by_parent(self):
        """Files in same immediate parent cluster together."""
        items = [
            _f("src/utils/a.py"),
            _f("src/utils/b.py"),
            _f("src/utils/c.py"),
            _f("src/core/x.py"),
        ]
        result = cluster_findings(items)
        clusters = [r for r in result if isinstance(r, FindingCluster)]
        standalone = [r for r in result if isinstance(r, Finding)]
        assert len(clusters) == 1
        assert clusters[0].common_path == "src/utils"
        assert len(standalone) == 1


class TestReportClustering:
    """Integration tests: clustered findings in the morning report."""

    def test_clustered_findings_show_collapsed(self):
        """3+ findings in same dir should appear in a collapsed <details> block."""
        items = [
            _f("src/a.py", title="Issue A"),
            _f("src/b.py", title="Issue B"),
            _f("src/c.py", title="Issue C"),
        ]
        report = generate_report(items, _make_run())
        assert "3 related findings" in report
        assert "<details>" in report
        assert "Issue A" in report
        assert "Issue B" in report
        assert "Issue C" in report

    def test_standalone_findings_not_collapsed(self):
        """Fewer than 3 findings in a dir should render normally."""
        items = [
            _f("src/a.py", title="Issue A"),
            _f("lib/b.py", title="Issue B"),
        ]
        report = generate_report(items, _make_run())
        assert "related findings" not in report
        assert "Issue A" in report
        assert "Issue B" in report

    def test_mixed_cluster_and_standalone_report(self):
        items = [
            _f("src/a.py", title="Clustered A"),
            _f("src/b.py", title="Clustered B"),
            _f("src/c.py", title="Clustered C"),
            _f("lib/d.py", title="Standalone D"),
        ]
        report = generate_report(items, _make_run())
        assert "3 related findings" in report
        assert "Clustered A" in report
        assert "Standalone D" in report

    def test_large_cluster_reduces_visual_lines(self):
        """A cluster of 10 findings should produce fewer top-level lines than
        10 individual findings."""
        clustered = [
            _f(f"src/{chr(97+i)}.py", title=f"Issue {i}")
            for i in range(10)
        ]
        report_clustered = generate_report(clustered, _make_run())
        # The clustered report should have "10 related findings" as a single summary
        assert "10 related findings" in report_clustered
        # All findings still present inside the collapsed cluster
        assert report_clustered.count("## MEDIUM") == 1

    def test_cluster_shows_directory_path(self):
        items = [
            _f("docs/guides/a.md", title="Link A"),
            _f("docs/guides/b.md", title="Link B"),
            _f("docs/guides/c.md", title="Link C"),
        ]
        report = generate_report(items, _make_run())
        assert "docs/guides" in report


# ── Pattern clustering tests ─────────────────────────────────────────


class TestNormalizeTitle:
    def test_strips_file_path(self):
        assert _normalize_title("TODO found in `src/main.py`") == "TODO found"

    def test_strips_line_number(self):
        assert _normalize_title("Unused import:42") == "Unused import"

    def test_strips_trailing_paren(self):
        assert _normalize_title("Stale link (was docs/old.md)") == "Stale link"

    def test_preserves_core_message(self):
        assert _normalize_title("[unused] func is unused") == "[unused] func is unused"

    def test_empty_string(self):
        assert _normalize_title("") == ""


class TestClusterByPattern:
    def test_groups_same_pattern(self):
        """Findings from the same detector with similar titles cluster."""
        items = [
            _f("src/a.py", detector="lint-runner", title="[F401] Unused import in `src/a.py`"),
            _f("src/b.py", detector="lint-runner", title="[F401] Unused import in `src/b.py`"),
            _f("src/c.py", detector="lint-runner", title="[F401] Unused import in `src/c.py`"),
        ]
        result = cluster_by_pattern(items)
        clusters = [r for r in result if isinstance(r, FindingCluster)]
        assert len(clusters) == 1
        assert clusters[0].cluster_type == "pattern"
        assert len(clusters[0].findings) == 3

    def test_different_detectors_not_grouped(self):
        """Same title pattern but different detectors → no cluster."""
        items = [
            _f("a.py", detector="lint-runner", title="Issue in `a.py`"),
            _f("b.py", detector="todo-scanner", title="Issue in `b.py`"),
            _f("c.py", detector="docs-drift", title="Issue in `c.py`"),
        ]
        result = cluster_by_pattern(items)
        # All standalone — different detectors
        assert all(isinstance(r, Finding) for r in result)

    def test_below_min_size_not_clustered(self):
        items = [
            _f("a.py", detector="lint-runner", title="Unused import in `a.py`"),
            _f("b.py", detector="lint-runner", title="Unused import in `b.py`"),
        ]
        result = cluster_by_pattern(items, min_size=3)
        assert all(isinstance(r, Finding) for r in result)

    def test_pattern_label(self):
        items = [
            _f("a.py", detector="docs-drift", title="Stale link in `README.md`"),
            _f("b.py", detector="docs-drift", title="Stale link in `GUIDE.md`"),
            _f("c.py", detector="docs-drift", title="Stale link in `API.md`"),
        ]
        result = cluster_by_pattern(items)
        clusters = [r for r in result if isinstance(r, FindingCluster)]
        assert len(clusters) == 1
        assert "docs-drift" in clusters[0].pattern_label
        assert "Stale link" in clusters[0].pattern_label

    def test_mixed_clusterable_and_standalone(self):
        items = [
            _f("a.py", detector="lint-runner", title="[F401] Unused import in `a.py`"),
            _f("b.py", detector="lint-runner", title="[F401] Unused import in `b.py`"),
            _f("c.py", detector="lint-runner", title="[F401] Unused import in `c.py`"),
            _f("d.py", detector="todo-scanner", title="TODO found"),
        ]
        result = cluster_by_pattern(items)
        clusters = [r for r in result if isinstance(r, FindingCluster)]
        standalone = [r for r in result if isinstance(r, Finding)]
        assert len(clusters) == 1
        assert len(standalone) == 1

    def test_empty_input(self):
        assert cluster_by_pattern([]) == []

    def test_min_size_one_returns_all_as_list(self):
        items = [_f("a.py")]
        result = cluster_by_pattern(items, min_size=1)
        assert len(result) == 1
