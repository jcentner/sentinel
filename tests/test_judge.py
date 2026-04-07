"""Tests for the LLM Judge (mocked Ollama)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from sentinel.core.judge import (
    _build_prompt,
    _parse_judgment,
    judge_findings,
)
from sentinel.models import Evidence, EvidenceType, Finding, Severity


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
    @patch("sentinel.core.judge.check_ollama")
    def test_graceful_degradation(self, mock_check):
        """When Ollama is unavailable, findings pass through unchanged."""
        mock_check.return_value = False
        findings = [_make_finding()]
        result = judge_findings(findings)
        assert len(result) == 1
        assert result[0].severity == Severity.LOW  # Unchanged

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_judge_confirms_finding(self, mock_check, mock_post):
        mock_check.return_value = True
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "response": json.dumps({
                    "is_real": True,
                    "adjusted_severity": "medium",
                    "summary": "Real issue",
                    "reasoning": "This TODO is old",
                }),
            },
            raise_for_status=lambda: None,
        )
        findings = [_make_finding()]
        result = judge_findings(findings)
        assert len(result) == 1
        assert result[0].severity == Severity.MEDIUM
        assert result[0].context["judge_verdict"] == "confirmed"
        # Verify structured output params sent to Ollama
        call_json = mock_post.call_args[1]["json"]
        assert call_json["format"] == "json"
        assert call_json["options"]["num_ctx"] == 2048

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_judge_marks_false_positive(self, mock_check, mock_post):
        mock_check.return_value = True
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "response": json.dumps({
                    "is_real": False,
                    "adjusted_severity": "low",
                    "summary": "Not real",
                    "reasoning": "Test expectation",
                }),
            },
            raise_for_status=lambda: None,
        )
        findings = [_make_finding(confidence=0.9)]
        result = judge_findings(findings)
        assert result[0].confidence <= 0.3
        assert result[0].context["judge_verdict"] == "likely_false_positive"

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_judge_error_fallback(self, mock_check, mock_post):
        mock_check.return_value = True
        mock_post.side_effect = Exception("Connection error")
        findings = [_make_finding()]
        result = judge_findings(findings)
        # Should return original finding on error
        assert len(result) == 1
        assert result[0].severity == Severity.LOW

    def test_empty_findings(self):
        result = judge_findings([])
        assert result == []

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_judge_logs_to_db(self, mock_check, mock_post, tmp_path):
        """When conn is provided, judge writes to llm_log table."""
        from sentinel.models import ScopeType
        from sentinel.store.db import get_connection
        from sentinel.store.llm_log import get_llm_log_for_run
        from sentinel.store.runs import create_run

        conn = get_connection(tmp_path / "test.db")
        run = create_run(conn, "/repo", ScopeType.FULL)

        mock_check.return_value = True
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "response": json.dumps({
                    "is_real": True,
                    "adjusted_severity": "high",
                    "summary": "Serious TODO",
                    "reasoning": "Old and critical",
                }),
                "eval_count": 55,
                "eval_duration": 1_200_000_000,
            },
            raise_for_status=lambda: None,
        )
        findings = [_make_finding(fingerprint="fp-test-123")]
        judge_findings(findings, conn=conn, run_id=run.id)

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

    @patch("httpx.post")
    @patch("sentinel.core.judge.check_ollama")
    def test_judge_error_logs_prompt_to_db(self, mock_check, mock_post, tmp_path):
        """On error, the prompt is still logged to llm_log."""
        from sentinel.models import ScopeType
        from sentinel.store.db import get_connection
        from sentinel.store.llm_log import get_llm_log_for_run
        from sentinel.store.runs import create_run

        conn = get_connection(tmp_path / "test.db")
        run = create_run(conn, "/repo", ScopeType.FULL)

        mock_check.return_value = True
        mock_post.side_effect = Exception("Connection error")
        findings = [_make_finding()]
        judge_findings(findings, conn=conn, run_id=run.id)

        rows = get_llm_log_for_run(conn, run.id)
        assert len(rows) == 1
        assert rows[0]["verdict"] == "error"
        assert rows[0]["prompt"] != ""  # prompt is captured even on error
        conn.close()
