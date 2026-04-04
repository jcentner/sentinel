"""Main application module."""

import os

# TODO: Add proper logging configuration
# This is a real TODO and should be caught.


def main():
    """Run the application."""
    # FIXME: Handle keyboard interrupt gracefully
    print("Starting myapp...")

    data = {"key": "value"}  # HACK: hardcoded data for now

    template = "# TODO: this is inside a string, not a real TODO"  # noqa

    # A tricky case: string then real comment on one line
    msg = "# TODO: fake"  # TODO: this IS a real comment TODO

    # This should be caught — HACK but no description
    # XXX

    return data


def helper():
    """A simple helper."""
    # This mentions TODO mid-sentence — should NOT be caught
    # We should find TODOs in the codebase eventually.

    # This is far from comment — should not count as TODO
    pass
