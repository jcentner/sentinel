"""Tests for the dependency audit detector."""

from __future__ import annotations

import json
import shutil
from unittest.mock import MagicMock, patch

import pytest

from sentinel.detectors.dep_audit import DepAudit
from sentinel.models import DetectorContext, DetectorTier, EvidenceType, Severity


@pytest.fixture
def auditor():
    return DepAudit()


SAMPLE_AUDIT_OUTPUT = json.dumps({
    "dependencies": [
        {
            "name": "requests",
            "version": "2.25.0",
            "vulns": [
                {
                    "id": "PYSEC-2023-001",
                    "description": "Certificate verification bypass",
                    "fix_versions": ["2.31.0"],
                }
            ],
        },
        {
            "name": "flask",
            "version": "2.0.0",
            "vulns": [],
        },
    ]
})


SAMPLE_MULTI_VULN = json.dumps({
    "dependencies": [
        {
            "name": "urllib3",
            "version": "1.26.0",
            "vulns": [
                {"id": "CVE-2023-001", "description": "SSRF vuln", "fix_versions": ["1.26.18"]},
                {"id": "CVE-2023-002", "description": "Header injection", "fix_versions": []},
            ],
        }
    ]
})


class TestDepAudit:
    def test_properties(self, auditor):
        assert auditor.name == "dep-audit"
        assert auditor.tier == DetectorTier.DETERMINISTIC
        assert "dependency" in auditor.categories

    @patch("sentinel.detectors.dep_audit.subprocess.run")
    def test_parses_vulnerabilities(self, mock_run, auditor, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["requests>=2.25"]\n'
        )
        mock_run.return_value = MagicMock(
            returncode=1, stdout=SAMPLE_AUDIT_OUTPUT, stderr=""
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = auditor.detect(ctx)
        assert len(findings) == 1  # Only requests has vulns
        assert "PYSEC-2023-001" in findings[0].title
        assert findings[0].severity == Severity.HIGH
        # Should use --requirement with a temp file (no requirements.txt)
        cmd = mock_run.call_args[0][0]
        assert "--requirement" in cmd

    @patch("sentinel.detectors.dep_audit.subprocess.run")
    def test_clean_dependencies(self, mock_run, auditor, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["safe>=1.0"]\n'
        )
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"dependencies": [{"name": "safe", "version": "1.0", "vulns": []}]}),
            stderr="",
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = auditor.detect(ctx)
        assert findings == []

    def test_not_python_project(self, auditor, tmp_path):
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = auditor.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.dep_audit.subprocess.run")
    def test_pip_audit_not_installed(self, mock_run, auditor, tmp_path):
        (tmp_path / "setup.py").write_text("")
        mock_run.side_effect = FileNotFoundError("pip-audit not found")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = auditor.detect(ctx)
        assert findings == []

    @patch("sentinel.detectors.dep_audit.subprocess.run")
    def test_multiple_vulns_per_package(self, mock_run, auditor, tmp_path):
        (tmp_path / "requirements.txt").write_text("urllib3==1.26.0\n")
        mock_run.return_value = MagicMock(
            returncode=1, stdout=SAMPLE_MULTI_VULN, stderr=""
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = auditor.detect(ctx)
        assert len(findings) == 2

    @patch("sentinel.detectors.dep_audit.subprocess.run")
    def test_evidence_content(self, mock_run, auditor, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["requests>=2.25"]\n'
        )
        mock_run.return_value = MagicMock(
            returncode=1, stdout=SAMPLE_AUDIT_OUTPUT, stderr=""
        )
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = auditor.detect(ctx)
        f = findings[0]
        assert f.evidence[0].type == EvidenceType.AUDIT_OUTPUT
        assert f.evidence[0].content
        assert "requests" in f.evidence[0].content
        assert "2.31.0" in f.evidence[0].content  # Fix version present

    @patch("sentinel.detectors.dep_audit.subprocess.run")
    def test_uses_requirements_file(self, mock_run, auditor, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.25.0\n")
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        ctx = DetectorContext(repo_root=str(tmp_path))
        auditor.detect(ctx)
        cmd = mock_run.call_args[0][0]
        assert "--requirement" in cmd

    def test_is_python_project_markers(self, auditor, tmp_path):
        assert not auditor._is_python_project(tmp_path)
        (tmp_path / "pyproject.toml").write_text("")
        assert auditor._is_python_project(tmp_path)

    def test_pyproject_no_deps_skips(self, auditor, tmp_path):
        """pyproject.toml without dependencies should skip (not audit current env)."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
        ctx = DetectorContext(repo_root=str(tmp_path))
        # Should return empty without calling pip-audit at all
        findings = auditor.detect(ctx)
        assert findings == []

    def test_extract_pyproject_deps(self, auditor, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["click>=8.0", "httpx>=0.27"]\n'
        )
        deps = auditor._extract_pyproject_deps(tmp_path)
        assert deps == ["click>=8.0", "httpx>=0.27"]

    def test_extract_pyproject_no_deps(self, auditor, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
        deps = auditor._extract_pyproject_deps(tmp_path)
        assert deps is None


class TestRealTool:
    @pytest.mark.skipif(
        not shutil.which("pip-audit"),
        reason="pip-audit not installed",
    )
    def test_real_pip_audit_on_clean_requirements(self, auditor, tmp_path):
        """Integration test: run real pip-audit on a safe requirements file."""
        (tmp_path / "requirements.txt").write_text("pip>=24.0\n")
        ctx = DetectorContext(repo_root=str(tmp_path))
        findings = auditor.detect(ctx)
        # pip is generally safe; should produce zero or minimal findings
        assert all(f.detector == "dep-audit" for f in findings)
