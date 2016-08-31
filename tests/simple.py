#!/usr/bin/env python3
"""Test that the simple hierarchy executes as expected."""

import difflib
import io
import unittest
from schedsi import textlog, world
from tests import common, simple_hierarchy

class TestExample(unittest.TestCase):
    """Test that the simple hierarchy executes as expected.

    Comparison is done via the text log, so that divergences can easily be checked."""

    def test_example(self):
        """Test that the simple hierarchy executes as expected."""
        text_buf = io.StringIO()
        text_log = textlog.TextLog(text_buf,
                                   textlog.TextLogAlign(cpu=1, time=3, module=7, thread=1))

        the_world = world.World(1, 10, simple_hierarchy.KERNEL, text_log)
        while the_world.step() < 400:
            pass

        expected = open("tests/simple_hierarchy.log", 'r')
        result = io.StringIO(text_buf.getvalue())
        diff = difflib.unified_diff(result.readlines(), expected.readlines(), "result", "expected")
        has_diff = False
        for line in common.color_diff(diff):
            has_diff = True
            print(line, end='')
        expected.close()
        self.assertFalse(has_diff)

if __name__ == '__main__':
    unittest.main()
