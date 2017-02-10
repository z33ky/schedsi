#!/usr/bin/env python3
"""Test that the simple hierarchy produces the expected graph SVG."""

import io
import os
import subprocess
import sys
import unittest
from schedsi import world
from schedsi.log import graphlog
from example import localtimer_kernel, singletimer_kernel


class TestExample(unittest.TestCase):
    """Test that the simple hierarchy produces the expected graph SVG."""

    def exec_world(self, log, *world_args, **world_kwargs):
        """Create and run a world and test the produced graph against a reference."""
        graph_log = graphlog.GraphLog()

        the_world = world.World(*world_args, graph_log, **world_kwargs)
        while the_world.step() <= 400:
            pass

        svg_buf = io.BytesIO()
        graph_log.write(svg_buf)
        compare_proc = ['compare', '-', log, '-metric', 'AE', os.devnull]
        compare = subprocess.Popen(compare_proc, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                   bufsize=0, cwd=os.path.dirname(sys.argv[0]))
        # graph_log.write(compare.stdin)
        _, out = compare.communicate(svg_buf.getvalue())
        compare.wait()
        self.assertEqual(compare.returncode, 0)
        self.assertEqual(out, b'0')

    def test_localtimer(self):
        """Test that the local timer hierarchy produces the expected graph SVG."""
        self.exec_world('local_timer_scheduling.svg', 1, localtimer_kernel.KERNEL.module,
                        local_timer_scheduling=True)

    def test_singletimer(self):
        """Test that the single timer hierarchy produces the expected graph SVG."""
        self.exec_world('single_timer_scheduling.svg', 1, singletimer_kernel.KERNEL.module,
                        local_timer_scheduling=False)


if __name__ == '__main__':
    unittest.main()
