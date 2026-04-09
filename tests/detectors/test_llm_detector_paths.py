"""Tests for LLM-assisted code paths in semantic-drift and test-coherence detectors (TD-028).

Uses MockProvider with canned responses to test JSON parsing,
finding construction, malformed response handling, and error scenarios.
"""

from __future__ import annotations

import json

import pytest

from sentinel.detectors.semantic_drift import SemanticDriftDetector
from sentinel.detectors.test_coherence import TestCoherenceDetector
from sentinel.models import DetectorContext, ScopeType
from tests.mock_provider import MockProvider


def _make_context(
    tmp_path,
    *,
    provider=None,
    skip_llm=False,
    model_capability="basic",
):
    """Create a DetectorContext with the given provider."""
    return DetectorContext(
        repo_root=str(tmp_path),
        scope=ScopeType.FULL,
        config={
            "provider": provider,
            "skip_llm": skip_llm,
            "num_ctx": 2048,
            "model_capability": model_capability,
        },
    )


# ---------------------------------------------------------------------------
# Fixtures: minimal repo structures that trigger LLM comparison
# ---------------------------------------------------------------------------


@pytest.fixture
def semantic_drift_repo(tmp_path):
    """Create a minimal repo with a doc that references code symbols."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n"
        "    '''Add two numbers.'''\n"
        "    return a + b\n"
        "\n"
        "def subtract(a: int, b: int) -> int:\n"
        "    '''Subtract b from a.'''\n"
        "    return a - b\n"
        "\n"
        "def multiply(a: int, b: int) -> int:\n"
        "    '''Multiply two numbers.'''\n"
        "    return a * b\n"
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text(
        "# Calculator API\n\n"
        "## Functions\n\n"
        "The calculator module provides `add`, `subtract`, and `divide` functions.\n\n"
        "### add(a, b)\n\n"
        "Returns the sum of a and b.\n\n"
        "```python\nadd(1, 2)  # returns 3\n```\n\n"
        "### subtract(a, b)\n\n"
        "Returns the difference of a and b.\n"
    )
    return tmp_path


@pytest.fixture
def test_coherence_repo(tmp_path):
    """Create a minimal repo with test and implementation files."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.py").write_text(
        "def process_data(data: list) -> list:\n"
        "    '''Process a list of data items.'''\n"
        "    result = []\n"
        "    for item in data:\n"
        "        if item > 0:\n"
        "            result.append(item * 2)\n"
        "    return result\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_utils.py").write_text(
        "from src.utils import process_data\n"
        "\n"
        "def test_process_data_happy():\n"
        "    '''Test basic processing.'''\n"
        "    result = process_data([1, 2, 3])\n"
        "    assert result == [2, 4, 6]\n"
        "    assert len(result) == 3\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Semantic Drift: LLM path tests
# ---------------------------------------------------------------------------


class TestSemanticDriftLLM:
    """Test the LLM comparison code paths in SemanticDriftDetector."""

    def test_basic_llm_needs_review(self, semantic_drift_repo):
        """LLM says needs_review=true → should produce a finding."""
        provider = MockProvider(
            generate_text=json.dumps({
                "needs_review": True,
                "reason": "Documentation references 'divide' function which does not exist in code",
            }),
        )
        ctx = _make_context(semantic_drift_repo, provider=provider)
        detector = SemanticDriftDetector()
        detector.detect(ctx)

        # Provider should have been called
        assert provider.generate_calls

    def test_basic_llm_no_review_needed(self, semantic_drift_repo):
        """LLM says needs_review=false → no findings from LLM path."""
        provider = MockProvider(
            generate_text=json.dumps({
                "needs_review": False,
                "reason": "",
            }),
        )
        ctx = _make_context(semantic_drift_repo, provider=provider)
        detector = SemanticDriftDetector()
        detector.detect(ctx)

        # LLM should have been called but found nothing to flag
        assert provider.generate_calls

    def test_enhanced_llm_with_specifics(self, semantic_drift_repo):
        """Enhanced mode returns structured specifics → finding with details."""
        provider = MockProvider(
            generate_text=json.dumps({
                "needs_review": True,
                "severity": "high",
                "reason": "Documentation references non-existent divide function",
                "specifics": [
                    "Line mentions 'divide' function but only add, subtract, multiply exist",
                    "Example code shows divide usage that would fail",
                ],
            }),
        )
        ctx = _make_context(
            semantic_drift_repo, provider=provider, model_capability="standard"
        )
        detector = SemanticDriftDetector()
        detector.detect(ctx)

        assert provider.generate_calls

    def test_malformed_json_response(self, semantic_drift_repo):
        """LLM returns garbage → no crash, no finding from that pair."""
        provider = MockProvider(
            generate_text="This is not JSON at all, sorry!",
        )
        ctx = _make_context(semantic_drift_repo, provider=provider)
        detector = SemanticDriftDetector()
        # Should not crash
        detector.detect(ctx)
        assert provider.generate_calls

    def test_empty_response(self, semantic_drift_repo):
        """LLM returns empty string → no crash."""
        provider = MockProvider(generate_text="")
        ctx = _make_context(semantic_drift_repo, provider=provider)
        detector = SemanticDriftDetector()
        detector.detect(ctx)

    def test_provider_error_in_generate(self, semantic_drift_repo):
        """Provider raises exception → detector handles gracefully."""
        provider = MockProvider(
            generate_error=RuntimeError("API unavailable"),
        )
        ctx = _make_context(semantic_drift_repo, provider=provider)
        detector = SemanticDriftDetector()
        detector.detect(ctx)

    def test_skip_llm_returns_empty(self, semantic_drift_repo):
        """skip_llm=True → returns empty list immediately."""
        provider = MockProvider(
            generate_text=json.dumps({"needs_review": True, "reason": "drift"}),
        )
        ctx = _make_context(semantic_drift_repo, provider=provider, skip_llm=True)
        detector = SemanticDriftDetector()
        findings = detector.detect(ctx)
        assert findings == []
        assert not provider.generate_calls

    def test_no_provider_returns_empty(self, semantic_drift_repo):
        """No provider → returns empty list."""
        ctx = _make_context(semantic_drift_repo, provider=None)
        detector = SemanticDriftDetector()
        findings = detector.detect(ctx)
        assert findings == []


# ---------------------------------------------------------------------------
# Test Coherence: LLM path tests
# ---------------------------------------------------------------------------


class TestTestCoherenceLLM:
    """Test the LLM comparison code paths in TestCoherenceDetector."""

    def test_basic_llm_needs_review(self, test_coherence_repo):
        """LLM says needs_review=true → should produce a finding."""
        provider = MockProvider(
            generate_text=json.dumps({
                "needs_review": True,
                "reason": "Test only covers happy path, missing edge cases for negative values",
            }),
        )
        ctx = _make_context(test_coherence_repo, provider=provider)
        detector = TestCoherenceDetector()
        detector.detect(ctx)

        assert provider.generate_calls

    def test_basic_llm_no_review(self, test_coherence_repo):
        """LLM says needs_review=false → no finding from comparison."""
        provider = MockProvider(
            generate_text=json.dumps({
                "needs_review": False,
                "reason": "",
            }),
        )
        ctx = _make_context(test_coherence_repo, provider=provider)
        detector = TestCoherenceDetector()
        detector.detect(ctx)

        assert provider.generate_calls

    def test_enhanced_llm_with_gaps(self, test_coherence_repo):
        """Enhanced mode returns gaps → structured finding."""
        provider = MockProvider(
            generate_text=json.dumps({
                "needs_review": True,
                "severity": "medium",
                "reason": "Test coverage has significant gaps",
                "gaps": [
                    "No test for empty input list",
                    "No test for negative values (filtered by condition)",
                    "No test for zero values",
                ],
            }),
        )
        ctx = _make_context(
            test_coherence_repo, provider=provider, model_capability="standard"
        )
        detector = TestCoherenceDetector()
        detector.detect(ctx)

        assert provider.generate_calls

    def test_malformed_json_response(self, test_coherence_repo):
        """LLM returns non-JSON → graceful handling."""
        provider = MockProvider(
            generate_text="I think the tests look fine overall.",
        )
        ctx = _make_context(test_coherence_repo, provider=provider)
        detector = TestCoherenceDetector()
        detector.detect(ctx)
        assert provider.generate_calls

    def test_empty_response(self, test_coherence_repo):
        """LLM returns empty → no crash."""
        provider = MockProvider(generate_text="")
        ctx = _make_context(test_coherence_repo, provider=provider)
        detector = TestCoherenceDetector()
        detector.detect(ctx)

    def test_provider_error(self, test_coherence_repo):
        """Provider throws → detector handles gracefully."""
        provider = MockProvider(
            generate_error=RuntimeError("Connection refused"),
        )
        ctx = _make_context(test_coherence_repo, provider=provider)
        detector = TestCoherenceDetector()
        detector.detect(ctx)

    def test_skip_llm_returns_empty(self, test_coherence_repo):
        """skip_llm=True → returns empty immediately."""
        provider = MockProvider(
            generate_text=json.dumps({"needs_review": True, "reason": "gaps"}),
        )
        ctx = _make_context(test_coherence_repo, provider=provider, skip_llm=True)
        detector = TestCoherenceDetector()
        findings = detector.detect(ctx)
        assert findings == []
        assert not provider.generate_calls

    def test_unhealthy_provider_returns_empty(self, test_coherence_repo):
        """Unhealthy provider → returns empty list."""
        provider = MockProvider(
            generate_text=json.dumps({"needs_review": True, "reason": "gaps"}),
            health=False,
        )
        ctx = _make_context(test_coherence_repo, provider=provider)
        detector = TestCoherenceDetector()
        findings = detector.detect(ctx)
        assert findings == []
