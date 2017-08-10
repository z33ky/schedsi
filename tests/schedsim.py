#!/usr/bin/env python3
"""Test that the schedsim tool executes as expected."""

import difflib
import io
import os
import subprocess
import sys
import unittest
from tests import common


class TestExample(unittest.TestCase):
    """Test that the schedsim tool executes as expected."""

    def exec_world(self, log, schedsim):
        """Create and run a world and test the produced log against a reference."""
        root = os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0])))
        schedsim_proc = ['python3', os.path.join(root, 'schedsim'),
                         os.path.join('tests', schedsim)]
        schedsim = subprocess.Popen(schedsim_proc, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    bufsize=0, cwd=root, encoding='utf-8')
        out, _ = schedsim.communicate()

        expected = open(os.path.join('tests', log), 'r')
        diff = difflib.unified_diff(out.splitlines(True), expected.readlines(),
                                    'result', 'expected')
        has_diff = False
        for line in common.color_diff(diff):
            has_diff = True
            print(line, end='')
        expected.close()
        self.assertFalse(has_diff)

    def test_localtimer(self):
        """Test that the local timer hierarchy executes as expected."""
        self.exec_world('local_timer_scheduling.log', 'localtimer.schedsim')

    def test_singletimer(self):
        """Test that the single timer hierarchy executes as expected."""
        self.exec_world('single_timer_scheduling.log', 'singletimer.schedsim')


if __name__ == '__main__':
    unittest.main()
