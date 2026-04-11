"""Tests for processing module — some are coherent, some have drifted."""

from myapp.processing import process_records


def test_process_empty_records():
    """Test processing an empty list returns empty results."""
    results, errors = process_records([], {})
    assert results == []
    assert errors == []


def test_process_valid_user():
    """Test processing a valid user record."""
    records = [{"id": 1, "type": "user", "email": "test@example.com"}]
    results, errors = process_records(records, {})
    assert len(results) == 1
    assert errors == []


def test_process_validates_xml_format():
    """Test that records are validated against XML schema.

    This test claims to check XML validation, but process_records
    has no XML handling at all — it processes dicts. This test
    description is completely out of sync with the implementation.
    """
    records = [{"id": 1, "type": "default"}]
    results, errors = process_records(records, {})
    assert len(results) == 1
