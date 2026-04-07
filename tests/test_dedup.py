"""Tests for finding fingerprinting and deduplication."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sentinel.core.dedup import (
    assign_fingerprints,
    compute_fingerprint,
    deduplicate,
)
from sentinel.models import (
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)
from sentinel.store.db import get_connection
from sentinel.store.findings import insert_finding, suppress_finding
from sentinel.store.runs import create_run


def _make_finding(**kwargs) -> Finding:
    defaults = {
        "detector": "test",
        "category": "code-quality",
        "severity": Severity.MEDIUM,
        "confidence": 0.8,
        "title": "Test issue",
        "description": "Something is wrong",
        "evidence": [Evidence(type=EvidenceType.CODE, source="x.py", content="bad")],
        "file_path": "src/x.py",
    }
    defaults.update(kwargs)
    return Finding(**defaults)


@pytest.fixture
def db_conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = get_connection(Path(tmpdir) / "test.db")
        yield conn
        conn.close()


class TestFingerprinting:
    def test_same_finding_same_fingerprint(self):
        f1 = _make_finding(title="F401: unused import")
        f2 = _make_finding(title="F401: unused import")
        assert compute_fingerprint(f1) == compute_fingerprint(f2)

    def test_different_findings_different_fingerprint(self):
        f1 = _make_finding(title="Issue A")
        f2 = _make_finding(title="Issue B")
        assert compute_fingerprint(f1) != compute_fingerprint(f2)

    def test_line_number_change_same_fingerprint(self):
        """Changing line numbers should NOT change the fingerprint."""
        f1 = _make_finding(line_start=10)
        f2 = _make_finding(line_start=20)
        assert compute_fingerprint(f1) == compute_fingerprint(f2)

    def test_different_file_different_fingerprint(self):
        f1 = _make_finding(file_path="a.py")
        f2 = _make_finding(file_path="b.py")
        assert compute_fingerprint(f1) != compute_fingerprint(f2)

    def test_assign_fingerprints(self):
        findings = [_make_finding(), _make_finding(title="Other")]
        assert all(f.fingerprint == "" for f in findings)
        assign_fingerprints(findings)
        assert all(f.fingerprint != "" for f in findings)
        assert findings[0].fingerprint != findings[1].fingerprint

    def test_assign_preserves_existing(self):
        f = _make_finding()
        f.fingerprint = "custom-fp"
        assign_fingerprints([f])
        assert f.fingerprint == "custom-fp"

    def test_fingerprint_length(self):
        fp = compute_fingerprint(_make_finding())
        assert len(fp) == 16  # Truncated hex

    def test_dep_audit_fingerprint_uses_vuln_id(self):
        f1 = _make_finding(
            detector="dep-audit",
            context={"vuln_id": "CVE-2023-001", "package": "requests"},
        )
        f2 = _make_finding(
            detector="dep-audit",
            context={"vuln_id": "CVE-2023-001", "package": "requests"},
            title="Different title",
        )
        assert compute_fingerprint(f1) == compute_fingerprint(f2)

    def test_lint_runner_same_file_different_violations(self):
        """Two lint violations in the same file must get different fingerprints."""
        f1 = _make_finding(
            detector="lint-runner",
            context={"rule": "F401"},
            title="F401: os imported but unused",
            file_path="src/main.py",
        )
        f2 = _make_finding(
            detector="lint-runner",
            context={"rule": "F401"},
            title="F401: sys imported but unused",
            file_path="src/main.py",
        )
        assert compute_fingerprint(f1) != compute_fingerprint(f2)

    def test_stale_ref_same_target_different_docs_dedup(self):
        """Two docs referencing the same missing file should get the same fingerprint."""
        f1 = _make_finding(
            detector="docs-drift",
            category="docs-drift",
            title="Stale path reference: `src/components/widget.tsx`",
            file_path="docs/plan-a.md",
            context={"pattern": "stale-inline-path", "referenced_path": "src/components/widget.tsx"},
        )
        f2 = _make_finding(
            detector="docs-drift",
            category="docs-drift",
            title="Stale path reference: `src/components/widget.tsx`",
            file_path="docs/plan-b.md",
            context={"pattern": "stale-inline-path", "referenced_path": "src/components/widget.tsx"},
        )
        assert compute_fingerprint(f1) == compute_fingerprint(f2)

    def test_stale_link_same_target_different_docs_dedup(self):
        """Two docs linking to the same missing file should get the same fingerprint."""
        f1 = _make_finding(
            detector="docs-drift",
            category="docs-drift",
            title="Stale link: [plan](phase-4.md)",
            file_path="docs/README.md",
            context={"pattern": "stale-reference", "target": "phase-4.md"},
        )
        f2 = _make_finding(
            detector="docs-drift",
            category="docs-drift",
            title="Stale link: [plan](phase-4.md)",
            file_path="docs/other.md",
            context={"pattern": "stale-reference", "target": "phase-4.md"},
        )
        assert compute_fingerprint(f1) == compute_fingerprint(f2)


class TestDeduplication:
    def test_filters_suppressed(self, db_conn):
        f = _make_finding()
        f.fingerprint = compute_fingerprint(f)
        suppress_finding(db_conn, f.fingerprint, reason="FP")

        result = deduplicate([f], db_conn)
        assert len(result) == 0

    def test_filters_within_run_dupes(self, db_conn):
        f1 = _make_finding()
        f1.fingerprint = "same-fp"
        f2 = _make_finding()
        f2.fingerprint = "same-fp"

        result = deduplicate([f1, f2], db_conn)
        assert len(result) == 1

    def test_marks_recurring(self, db_conn):
        # Insert a finding in a prior run
        run = create_run(db_conn, "/tmp/repo")
        prior = _make_finding()
        prior.fingerprint = "recurring-fp"
        insert_finding(db_conn, run.id, prior)

        # New finding with same fingerprint
        new = _make_finding()
        new.fingerprint = "recurring-fp"
        result = deduplicate([new], db_conn)
        assert len(result) == 1
        assert result[0].context.get("recurring") is True

    def test_passes_new_findings(self, db_conn):
        f = _make_finding()
        f.fingerprint = "brand-new-fp"
        result = deduplicate([f], db_conn)
        assert len(result) == 1
        assert not result[0].context or not result[0].context.get("recurring")
