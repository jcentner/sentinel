"""Tests for utility functions — mix of coherent and drifted tests."""

from myapp.utils import (
    clamp,
    deep_merge,
    format_currency,
    hash_file,
    normalize_whitespace,
    parse_date,
    retry,
    slugify,
    validate_email,
)


def test_format_currency_returns_string():
    """Test that format_currency returns a formatted dollar string.

    Expects output like '$12.50' for USD amounts.
    """
    # DRIFT: function returns integer cents, not a string
    result = format_currency(12.50)
    assert isinstance(result, str)
    assert "$" in result


def test_parse_date_iso():
    """Test parsing an ISO 8601 date string."""
    result = parse_date("2024-01-15")
    assert result["year"] == 2024
    assert result["month"] == 1
    assert result["day"] == 15


def test_parse_date_rfc2822():
    """Test parsing an RFC 2822 date string.

    The function should handle 'Mon, 15 Jan 2024' format.
    """
    # DRIFT: function only handles ISO 8601, this would raise ValueError
    result = parse_date("2024-06-01")
    assert result["year"] == 2024


def test_slugify():
    """Test URL slug generation from text."""
    assert slugify("Hello World") == "hello-world"
    assert slugify("  Lots  of   Spaces  ") == "lots-of-spaces"


def test_validate_email():
    """Test email validation with valid and invalid inputs."""
    assert validate_email("user@example.com")
    assert not validate_email("invalid-email")
    assert not validate_email("@no-local.com")


def test_retry_exponential_backoff():
    """Test that retry uses exponential backoff between attempts.

    Each retry should wait twice as long as the previous one.
    """
    # DRIFT: function uses fixed delay, not exponential backoff
    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("not yet")
        return "ok"

    result = retry(flaky, max_retries=3, delay=0.01)
    assert result == "ok"


def test_deep_merge():
    """Test recursive dictionary merging."""
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}, "e": 5}
    result = deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}


def test_hash_file_sha256(tmp_path):
    """Test that hash_file returns a SHA-256 hex digest.

    The digest should be 64 characters of lowercase hex.
    """
    # DRIFT: function uses MD5 (32 chars), not SHA-256 (64 chars)
    p = tmp_path / "test.txt"
    p.write_text("hello")
    result = hash_file(str(p))
    assert len(result) == 64  # SHA-256 digest length


def test_normalize_whitespace():
    """Test whitespace normalization."""
    assert normalize_whitespace("  hello   world  ") == "hello world"
    assert normalize_whitespace("tabs\there") == "tabs here"


def test_clamp():
    """Test numeric clamping."""
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(15, 0, 10) == 10
