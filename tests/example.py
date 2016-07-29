#!/usr/bin/env python3
"""Test that the example executes as expected."""

import difflib
import subprocess
import unittest

def color_diff(diff):
    """Colorize diff output."""
    for line in diff:
        if line.startswith("+"):
            yield "[32;1m" + line + "[0m"
        elif line.startswith("-"):
            yield "[34;1m" + line + "[0m"
        else:
            yield line

class TestExample(unittest.TestCase):
    """Test that the example executes as expected."""

    def test_example(self):
        """Test that the example executes as expected."""
        example = subprocess.Popen(["example/kernel.py", "-"], stdout=subprocess.PIPE)
        expected = open("tests/kernel.log", 'r')
        result = list(map(lambda l: l.decode("utf-8"), example.stdout.readlines()))
        diff = difflib.unified_diff(result, expected.readlines(), "result", "expected")
        okay = True
        if diff:
            for line in color_diff(diff):
                okay = False
                print(line, end='')
        example.stdout.close()
        expected.close()
        self.assertTrue(okay)

if __name__ == '__main__':
    unittest.main()
