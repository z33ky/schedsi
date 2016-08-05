#!/usr/bin/env python3
"""Some miscellaneous functionality for the tests."""

def color_diff(diff):
    """Colorize diff output."""
    for line in diff:
        if line.startswith("+"):
            yield "[32;1m" + line + "[0m"
        elif line.startswith("-"):
            yield "[34;1m" + line + "[0m"
        else:
            yield line
