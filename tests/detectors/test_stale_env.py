"""Tests for the stale config / env drift detector."""

from __future__ import annotations

import pytest

from sentinel.detectors.stale_env import StaleEnv
from sentinel.models import DetectorContext, DetectorTier


@pytest.fixture
def detector():
    return StaleEnv()


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


# ── Documented but unused ───────────────────────────────────────────


class TestDocumentedButUnused:
    def test_basic_stale_var(self, detector, make_context, tmp_path):
        """Documented var not referenced in code produces a finding."""
        (tmp_path / ".env.example").write_text(
            "DATABASE_URL=postgres://...\nSECRET_KEY=changeme\n"
        )
        (tmp_path / "app.py").write_text(
            'import os\ndb = os.environ.get("DATABASE_URL")\n'
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        titles = {f.title for f in findings}
        assert "Documented env var never used: SECRET_KEY" in titles
        assert len(findings) == 1

    def test_no_stale_when_all_used(self, detector, make_context, tmp_path):
        """No findings when all documented vars are referenced."""
        (tmp_path / ".env.example").write_text(
            "DATABASE_URL=\nSECRET_KEY=\n"
        )
        (tmp_path / "app.py").write_text(
            'import os\n'
            'os.environ["DATABASE_URL"]\n'
            'os.getenv("SECRET_KEY")\n'
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_env_sample_file(self, detector, make_context, tmp_path):
        """Works with .env.sample filename."""
        (tmp_path / ".env.sample").write_text("API_KEY=xxx\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert any("API_KEY" in f.title for f in findings)

    def test_env_template_file(self, detector, make_context, tmp_path):
        """Works with .env.template filename."""
        (tmp_path / ".env.template").write_text("API_KEY=xxx\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert any("API_KEY" in f.title for f in findings)

    def test_common_env_vars_skipped(self, detector, make_context, tmp_path):
        """System vars like PATH, HOME are not flagged."""
        (tmp_path / ".env.example").write_text(
            "PATH=/usr/bin\nHOME=/root\nMY_APP_KEY=secret\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        titles = {f.title for f in findings}
        assert "Documented env var never used: PATH" not in titles
        assert "Documented env var never used: HOME" not in titles
        assert "Documented env var never used: MY_APP_KEY" in titles


# ── Undocumented vars ───────────────────────────────────────────────


class TestUndocumentedVars:
    def test_code_var_not_in_example(self, detector, make_context, tmp_path):
        """Code references var not in .env.example."""
        (tmp_path / ".env.example").write_text("DATABASE_URL=\n")
        (tmp_path / "app.py").write_text(
            'import os\n'
            'os.environ["DATABASE_URL"]\n'
            'os.getenv("NEW_SECRET")\n'
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        titles = {f.title for f in findings}
        assert "Undocumented env var: NEW_SECRET" in titles
        assert len(findings) == 1

    def test_undocumented_has_medium_severity(self, detector, make_context, tmp_path):
        """Undocumented vars are medium severity (higher than stale)."""
        from sentinel.models import Severity

        (tmp_path / ".env.example").write_text("EXISTING_VAR=\n")
        (tmp_path / "app.py").write_text(
            'import os\nos.getenv("EXISTING_VAR")\nos.getenv("MISSING_VAR")\n'
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert findings[0].severity == Severity.MEDIUM


# ── Python patterns ─────────────────────────────────────────────────


class TestPythonPatterns:
    def test_os_environ_bracket(self, detector, make_context, tmp_path):
        """os.environ["VAR"] is detected."""
        (tmp_path / ".env.example").write_text("MY_VAR=\n")
        (tmp_path / "app.py").write_text('import os\nos.environ["MY_VAR"]\n')
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_os_environ_get(self, detector, make_context, tmp_path):
        """os.environ.get("VAR") is detected."""
        (tmp_path / ".env.example").write_text("MY_VAR=\n")
        (tmp_path / "app.py").write_text('import os\nos.environ.get("MY_VAR")\n')
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_os_getenv(self, detector, make_context, tmp_path):
        """os.getenv("VAR") is detected."""
        (tmp_path / ".env.example").write_text("MY_VAR=\n")
        (tmp_path / "app.py").write_text('import os\nos.getenv("MY_VAR")\n')
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_nested_python_files(self, detector, make_context, tmp_path):
        """Scans nested directories."""
        (tmp_path / ".env.example").write_text("DEEP_VAR=\n")
        sub = tmp_path / "src" / "app"
        sub.mkdir(parents=True)
        (sub / "config.py").write_text('import os\nos.getenv("DEEP_VAR")\n')
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0


# ── JS/TS patterns ──────────────────────────────────────────────────


class TestJsPatterns:
    def test_process_env_dot(self, detector, make_context, tmp_path):
        """process.env.VAR is detected."""
        (tmp_path / ".env.example").write_text("API_URL=\n")
        (tmp_path / "config.ts").write_text(
            "const url = process.env.API_URL;\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_process_env_bracket(self, detector, make_context, tmp_path):
        """process.env["VAR"] is detected."""
        (tmp_path / ".env.example").write_text("API_URL=\n")
        (tmp_path / "config.js").write_text(
            'const url = process.env["API_URL"];\n'
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_tsx_file(self, detector, make_context, tmp_path):
        """Scans .tsx files."""
        (tmp_path / ".env.example").write_text("NEXT_PUBLIC_API=\n")
        (tmp_path / "page.tsx").write_text(
            "const api = process.env.NEXT_PUBLIC_API;\n"
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0


# ── Edge cases ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_no_env_example(self, detector, make_context, tmp_path):
        """No findings when no .env.example exists."""
        (tmp_path / "app.py").write_text('import os\nos.getenv("SECRET")\n')
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_empty_env_example(self, detector, make_context, tmp_path):
        """No findings with empty/comments-only .env.example."""
        (tmp_path / ".env.example").write_text("# Just a comment\n\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_comments_in_env_file(self, detector, make_context, tmp_path):
        """Comments in .env.example are ignored."""
        (tmp_path / ".env.example").write_text(
            "# Database config\nDATABASE_URL=\n# API settings\nAPI_KEY=\n"
        )
        (tmp_path / "app.py").write_text(
            'import os\nos.getenv("DATABASE_URL")\nos.getenv("API_KEY")\n'
        )
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 0

    def test_mixed_python_and_js(self, detector, make_context, tmp_path):
        """Scans both Python and JS files."""
        (tmp_path / ".env.example").write_text(
            "PY_VAR=\nJS_VAR=\nUNUSED_VAR=\n"
        )
        (tmp_path / "app.py").write_text('import os\nos.getenv("PY_VAR")\n')
        (tmp_path / "config.js").write_text("const x = process.env.JS_VAR;\n")
        ctx = make_context()
        findings = detector.detect(ctx)
        assert len(findings) == 1
        assert "UNUSED_VAR" in findings[0].title

    def test_skips_venv(self, detector, make_context, tmp_path):
        """Files in .venv are not scanned."""
        (tmp_path / ".env.example").write_text("MY_VAR=\n")
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "site.py").write_text('import os\nos.getenv("MY_VAR")\n')
        ctx = make_context()
        findings = detector.detect(ctx)
        # .venv shouldn't count, so MY_VAR should be flagged as stale
        assert any("MY_VAR" in f.title for f in findings)


# ── Detector metadata ───────────────────────────────────────────────


class TestDetectorMeta:
    def test_name(self, detector):
        assert detector.name == "stale-env"

    def test_tier(self, detector):
        assert detector.tier == DetectorTier.DETERMINISTIC

    def test_categories(self, detector):
        assert "config" in detector.categories

    def test_registered(self):
        from sentinel.detectors.base import get_detector
        d = get_detector("stale-env")
        assert d is not None
