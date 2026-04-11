"""Tests for main module — intentionally drifted for test-coherence detection."""

from myapp.main import main


def test_main_runs():
    """Test that main function executes without error."""
    result = main()
    assert result is not None


def test_main_returns_data():
    """Test that main returns processed data.

    This test checks that the return value contains expected keys,
    but the implementation just returns a raw dict — the test
    asserts behavior that doesn't match implementation.
    """
    result = main()
    assert isinstance(result, dict)
    assert "key" in result


def test_old_handler():
    """Test the old_handler function.

    This test references a function that no longer exists in main.py.
    The old_handler was removed but this test was never updated.
    This is a test-code coherence issue.
    """
    # This would fail at runtime — tests a removed function
    pass


def test_keyboard_interrupt_handling():
    """Test graceful keyboard interrupt handling.

    Tests that main() catches KeyboardInterrupt and exits cleanly.
    But main() doesn't actually handle KeyboardInterrupt — there's
    a FIXME comment about it but no implementation.
    """
    result = main()
    assert result is not None
