#!/usr/bin/env python3
"""Test that the simple hierarchy executes as expected."""

import difflib
import io
import unittest
from schedsi import textlog, world
from tests import common
from example import localtimer_kernel, singletimer_kernel, penalty_scheduler


class TestExample(unittest.TestCase):
    """Test that the simple hierarchy executes as expected.

    Comparison is done via the text log, so that divergences can easily be checked.
    """
    textlog_align = textlog.TextLogAlign(cpu=1, time=3, module=7, thread=1)

    def exec_world(self, log, *world_args, **world_kwargs):
        """Create and run a world and test the produced log against a reference."""
        text_buf = io.StringIO()
        text_log = textlog.TextLog(text_buf, self.textlog_align)

        the_world = world.World(*world_args, text_log, **world_kwargs)
        while the_world.step() <= 400:
            pass

        the_world.log_statistics()

        expected = open('tests/' + log, 'r')
        text_buf.seek(0)
        diff = difflib.unified_diff(text_buf.readlines(), expected.readlines(),
                                    'result', 'expected')
        has_diff = False
        for line in common.color_diff(diff):
            has_diff = True
            print(line, end='')
        expected.close()
        self.assertFalse(has_diff)

    def test_localtimer(self):
        """Test that the local timer hierarchy executes as expected."""
        self.exec_world('local_timer_scheduling.log', 1, localtimer_kernel.KERNEL.module,
                        local_timer_scheduling=True)

    def test_singletimer(self):
        """Test that the single timer hierarchy executes as expected."""
        self.exec_world('single_timer_scheduling.log', 1, singletimer_kernel.KERNEL.module,
                        local_timer_scheduling=False)

    def test_penalty_scheduler(self):
        """Test that the penalty scheduler executes as expected."""
        self.exec_world('penalty_scheduling.log', 1, penalty_scheduler.KERNEL.module,
                        local_timer_scheduling=False)


if __name__ == '__main__':
    unittest.main()
