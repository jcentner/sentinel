"""Tests for the LLM Judge (mocked provider)."""

from __future__ import annotations

from sentinel.core.judge import (
    _build_prompt,
    _parse_judgment,
    judge_findings,
)
from sentinel.models import Evidence, EvidenceType, Finding, Severity
from tests.mock_provider import make_judge_provider


def _make_finding(**kwargs) -> Finding:
    defaults = {
        "detector": "todo-scanner",
        "category": "todo-fixme",
        "severity": Severity.LOW,
        "confidence": 0.9,
        "title": "TODO: fix this",
        "description": "A todo comment",
        "evidence": [Evidence(type=EvidenceType.CODE, source="x.py", content="# TODO: fix")],
        "file_path": "src/x.py",
        "line_start": 10,
    }
    defaults.update(kwargs)
    return Finding(**defaults)


class TestPromptBuilding:
    def test_build_prompt(self):
        f = _make_finding()
        prompt = _build_prompt(f)
        assert "todo-scanner" in prompt
        assert "TODO: fix this" in prompt
        assert "src/x.py" in prompt


class TestJudgmentParsing:
    def test_parse_clean_json(self):
        text = '{"is_real": true, "adjusted_severity": "medium", "summary": "Real issue", "reasoning": "Because"}'
        result = _parse_judgment(text)
        assert result is not None
        assert result["is_real"] is True
        assert result["adjusted_severity"] == "medium"

    def test_parse_json_in_code_block(self):
        text = '```json\n{"is_real": false, "adjusted_severity": "low", "summary": "FP", "reasoning": "Not real"}\n```'
        result = _parse_judgment(text)
        assert result is not None
        assert result["is_real"] is False

    def test_parse_json_with_surrounding_text(self):
        text = 'Here is my analysis:\n{"is_real": true, "adjusted_severity": "high", "summary": "Serious", "reasoning": "Bad"}\nThat is all.'
        result = _parse_judgment(text)
        assert result is not None
        assert result["adjusted_severity"] == "high"

    def test_parse_no_json(self):
        result = _parse_judgment("This is just text without JSON")
        assert result is None

    def test_parse_invalid_json(self):
        result = _parse_judgment("{invalid json}")
        assert result is None


class TestJudgeFindings:
    def test_graceful_degradation(self):
        """When provider is unavailable, findings pass through unchanged."""
        provider = make_judge_provider(health=False)
        findings = [_make_finding()]
        result = judge_findings(findings, provider=provider)
        assert len(result) == 1
        assert result[0].severity == Severity.LOW  # Unchanged

    def test_judge_confirms_finding(self):
        provider = make_judge_provider(
            is_real=True,
            adjusted_severity="medium",
        )
        findings = [_make_finding()]
        result = judge_findings(findings, provider=provider)
        assert len(result) == 1
        assert result[0].severity == Severity.MEDIUM
        assert result[0].context["judge_verdict"] == "confirmed"
        # Verify json_output was requested
        assert provider.generate_calls[0]["json_output"] is True
        assert provider.generate_calls[0]["num_ctx"] == 2048

    def test_judge_custom_num_ctx(self):
        provider = make_judge_provider(is_real=True, adjusted_severity="medium")
        findings = [_make_finding()]
        judge_findings(findings, provider=provider, num_ctx=4096)
        assert provider.generate_calls[0]["num_ctx"] == 4096

    def test_judge_marks_false_positive(self):
        provider = make_judge_provider(is_real=False, adjusted_severity="low")
        findings = [_make_finding(confidence=0.9)]
        result = judge_findings(findings, provider=provider)
        assert result[0].confidence <= 0.3
        assert result[0].context["judge_verdict"] == "likely_false_positive"

    def test_judge_error_fallback(self):
        provider = make_judge_provider(error=Exception("Connection error"))
        findings = [_make_finding()]
        result = judge_findings(findings, provider=provider)
        # Should return original finding on error
        assert len(result) == 1
        assert result[0].severity == Severity.LOW

    def test_empty_findings(self):
        provider = make_judge_provider()
        result = judge_findings([], provider=provider)
        assert result == []

    def test_judge_logs_to_db(self, tmp_path):
        """When conn is provided, judge writes to llm_log table."""
        from sentinel.models import ScopeType
        from sentinel.store.db import get_connection
        from sentinel.store.llm_log import get_llm_log_for_run
        from sentinel.store.runs import create_run

        conn = get_connection(tmp_path / "test.db")
        run = create_run(conn, "/repo", ScopeType.FULL)

        provider = make_judge_provider(
            is_real=True,
            adjusted_severity="high",
            summary="Serious TODO",
            reasoning="Old and critical",
            token_count=55,
            duration_ms=1200.0,
        )
        findings = [_make_finding(fingerprint="fp-test-123")]
        judge_findings(findings, provider=provider, conn=conn, run_id=run.id)

        rows = get_llm_log_for_run(conn, run.id)
        assert len(rows) == 1
        row = rows[0]
        assert row["purpose"] == "judge"
        assert row["verdict"] == "confirmed"
        assert row["is_real"] == 1
        assert row["adjusted_severity"] == "high"
        assert row["finding_fingerprint"] == "fp-test-123"
        assert row["tokens_generated"] == 55
        assert row["prompt"] != ""
        conn.close()

    def test_judge_error_logs_prompt_to_db(self, tmp_path):
        """On error, the prompt is still logged to llm_log."""
        from sentinel.models import ScopeType
        from sentinel.store.db import get_connection
        from sentinel.store.llm_log import get_llm_log_for_run
        from sentinel.store.runs import create_run

        conn = get_connection(tmp_path / "test.db")
        run = create_run(conn, "/repo", ScopeType.FULL)

        provider = make_judge_provider(error=Exception("Connection error"))
        findings = [_make_finding()]
        judge_findings(findings, provider=provider, conn=conn, run_id=run.id)

        rows = get_llm_log_for_run(conn, run.id)
        assert len(rows) == 1
        assert rows[0]["verdict"] == "error"
        assert rows[0]["prompt"] != ""  # prompt is captured even on error
        conn.close()
