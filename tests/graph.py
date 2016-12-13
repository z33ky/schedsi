#!/usr/bin/env python3
"""Test that the simple hierarchy produces the expected graph SVG."""

import io
import os
import subprocess
import sys
import unittest
from schedsi import graphlog, world
from tests import simple_hierarchy

COMPARE = ['compare', '-', 'simple_hierarchy.svg', '-metric', 'AE', os.devnull]


class TestExample(unittest.TestCase):
    """Test that the simple hierarchy produces the expected graph SVG."""

    def test_example(self):
        """Test that the simple hierarchy produces the expected graph SVG."""
        graph_log = graphlog.GraphLog()

        the_world = world.World(1, simple_hierarchy.KERNEL, graph_log, local_timer_scheduling=False)
        while the_world.step() <= 400:
            pass

        svg_buf = io.BytesIO()
        graph_log.write(svg_buf)
        compare = subprocess.Popen(COMPARE, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                   bufsize=0, cwd=os.path.dirname(sys.argv[0]))
        # graph_log.write(compare.stdin)
        _, out = compare.communicate(svg_buf.getvalue())
        compare.wait()
        self.assertEqual(compare.returncode, 0)
        self.assertEqual(out, b'0')


if __name__ == '__main__':
    unittest.main()
