"""Tests for the CI/CD config drift detector."""

from __future__ import annotations

import pytest

from sentinel.detectors.cicd_drift import CicdDrift
from sentinel.models import DetectorContext, DetectorTier


@pytest.fixture
def detector():
    return CicdDrift()


@pytest.fixture
def make_context(tmp_path):
    """Factory for DetectorContext pointing at a tmp repo."""

    def _make(**kwargs):
        defaults = {
            "repo_root": str(tmp_path),
            "config": {},
            "target_paths": None,
            "changed_files": None,
        }
        defaults.update(kwargs)
        return DetectorContext(**defaults)

    return _make


# ── Metadata ────────────────────────────────────────────────────────


class TestMetadata:
    def test_name(self, detector):
        assert detector.name == "cicd-drift"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, detector):
        assert "config-drift" in detector.categories


# ── GitHub Actions ──────────────────────────────────────────────────


class TestGitHubActions:
    def test_no_workflows_dir(self, detector, make_context, tmp_path):
        """No findings when .github/workflows/ doesn't exist."""
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_stale_local_action(self, detector, make_context, tmp_path):
        """Local action reference (uses: ./) that doesn't exist."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: ./.github/actions/my-action\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "my-action" in findings[0].title
        assert findings[0].line_start == 4

    def test_valid_local_action(self, detector, make_context, tmp_path):
        """Local action that exists produces no finding."""
        action_dir = tmp_path / ".github" / "actions" / "my-action"
        action_dir.mkdir(parents=True)
        (action_dir / "action.yml").write_text("name: test\n")
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "steps:\n"
            "  - uses: ./.github/actions/my-action\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_remote_action_ignored(self, detector, make_context, tmp_path):
        """Remote actions (uses: owner/repo@ref) are not checked."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "steps:\n"
            "  - uses: actions/checkout@v4\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_stale_working_directory(self, detector, make_context, tmp_path):
        """working-directory pointing to missing dir."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    defaults:\n"
            "      run:\n"
            "        working-directory: apps/frontend\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "apps/frontend" in findings[0].title
        assert "working-directory" in findings[0].title

    def test_valid_working_directory(self, detector, make_context, tmp_path):
        """working-directory pointing to existing dir produces no finding."""
        (tmp_path / "apps" / "frontend").mkdir(parents=True)
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "working-directory: apps/frontend\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_dynamic_value_skipped(self, detector, make_context, tmp_path):
        """Templated values (${{ ... }}) are not checked."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "working-directory: ${{ github.workspace }}/app\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_absolute_path_skipped(self, detector, make_context, tmp_path):
        """Absolute paths like /usr/local/bin are not checked."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "path: /usr/local/bin\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_tilde_path_skipped(self, detector, make_context, tmp_path):
        """Home-relative paths like ~/.npm are not checked."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "path: ~/.npm\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_stale_file_key(self, detector, make_context, tmp_path):
        """file: key (e.g. docker/build-push-action) with missing path."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "steps:\n"
            "  - uses: docker/build-push-action@v5\n"
            "    with:\n"
            "      file: docker/Dockerfile.prod\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "docker/Dockerfile.prod" in findings[0].title

    def test_stale_path_key(self, detector, make_context, tmp_path):
        """path: key in with: block pointing to missing path."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "steps:\n"
            "  - uses: actions/cache@v3\n"
            "    with:\n"
            "      path: vendor/bundle\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "vendor/bundle" in findings[0].title

    def test_glob_path_skipped(self, detector, make_context, tmp_path):
        """Glob patterns in path values are not checked."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "path: src/**/*.py\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_multiple_findings(self, detector, make_context, tmp_path):
        """Multiple stale references in one file produce multiple findings."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: ./.github/actions/missing1\n"
            "      - uses: ./.github/actions/missing2\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 2

    def test_non_yml_files_ignored(self, detector, make_context, tmp_path):
        """Non-YAML files in workflows dir are ignored."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "README.md").write_text("# Workflows\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0


# ── Dockerfiles ─────────────────────────────────────────────────────


class TestDockerfiles:
    def test_no_dockerfile(self, detector, make_context, tmp_path):
        """No findings when no Dockerfile exists."""
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_stale_copy_source(self, detector, make_context, tmp_path):
        """COPY source path that doesn't exist."""
        (tmp_path / "Dockerfile").write_text(
            "FROM node:18\n"
            "COPY package.json /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "package.json" in findings[0].title
        assert findings[0].line_start == 2

    def test_valid_copy_source(self, detector, make_context, tmp_path):
        """COPY source that exists produces no finding."""
        (tmp_path / "package.json").write_text("{}\n")
        (tmp_path / "Dockerfile").write_text(
            "FROM node:18\n"
            "COPY package.json /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_add_stale_source(self, detector, make_context, tmp_path):
        """ADD source path that doesn't exist."""
        (tmp_path / "Dockerfile").write_text(
            "FROM ubuntu\n"
            "ADD config.tar.gz /opt/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "config.tar.gz" in findings[0].title

    def test_add_url_ignored(self, detector, make_context, tmp_path):
        """ADD with a URL source is not checked."""
        (tmp_path / "Dockerfile").write_text(
            "FROM ubuntu\n"
            "ADD https://example.com/file.tar.gz /opt/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_copy_with_variable_skipped(self, detector, make_context, tmp_path):
        """COPY with build arg variable is not checked."""
        (tmp_path / "Dockerfile").write_text(
            "FROM ubuntu\n"
            "ARG SRC_DIR=src\n"
            "COPY $SRC_DIR /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_copy_from_multistage_skipped(self, detector, make_context, tmp_path):
        """COPY --from=stage references are not checked as local paths."""
        (tmp_path / "Dockerfile").write_text(
            "FROM golang AS builder\n"
            "RUN go build -o /app\n"
            "FROM alpine\n"
            "COPY --from=builder /app /app\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_copy_glob_skipped(self, detector, make_context, tmp_path):
        """COPY with glob pattern is not checked."""
        (tmp_path / "Dockerfile").write_text(
            "FROM node:18\n"
            "COPY *.json /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_copy_current_dir_skipped(self, detector, make_context, tmp_path):
        """COPY . . is not flagged."""
        (tmp_path / "Dockerfile").write_text(
            "FROM node:18\n"
            "COPY . /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_dockerfile_variants(self, detector, make_context, tmp_path):
        """Detect issues in Dockerfile.dev, Dockerfile.prod, etc."""
        (tmp_path / "Dockerfile.dev").write_text(
            "FROM node:18\n"
            "COPY missing-dir /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1

    def test_nested_dockerfile(self, detector, make_context, tmp_path):
        """Dockerfiles in subdirectories are also checked."""
        docker_dir = tmp_path / "services" / "api"
        docker_dir.mkdir(parents=True)
        (docker_dir / "Dockerfile").write_text(
            "FROM python:3.12\n"
            "COPY missing.txt /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "services/api/Dockerfile" in findings[0].file_path

    def test_nested_dockerfile_relative_to_own_dir(self, detector, make_context, tmp_path):
        """COPY source found relative to Dockerfile dir is not flagged."""
        docker_dir = tmp_path / "services" / "api"
        docker_dir.mkdir(parents=True)
        (docker_dir / "requirements.txt").write_text("flask\n")
        (docker_dir / "Dockerfile").write_text(
            "FROM python:3.12\n"
            "COPY requirements.txt /app/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_copy_with_chown_flag(self, detector, make_context, tmp_path):
        """COPY --chown=user:group still checks the source path."""
        (tmp_path / "Dockerfile").write_text(
            "FROM node:18\n"
            "COPY --chown=node:node missing.conf /etc/\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "missing.conf" in findings[0].title


# ── Finding Structure ───────────────────────────────────────────────


class TestFindingStructure:
    def test_finding_fields(self, detector, make_context, tmp_path):
        """Verify finding has correct metadata."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "working-directory: nonexistent\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        f = findings[0]
        assert f.detector == "cicd-drift"
        assert f.category == "config-drift"
        assert f.severity.value == "medium"
        assert f.confidence == 0.90
        assert f.file_path == ".github/workflows/ci.yml"
        assert f.evidence[0].type.value == "config"
        assert f.evidence[0].line_range == (1, 1)

    def test_exception_returns_empty(self, detector, make_context, tmp_path, monkeypatch):
        """Exceptions in detect() are caught and return empty list."""
        monkeypatch.setattr(
            detector, "_run", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert findings == []
