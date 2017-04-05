#!/usr/bin/env python3
"""Test that the simple hierarchy executes as expected."""

import difflib
import importlib
import io
import unittest
from schedsi import world
from schedsi.log import textlog
from tests import common


class TestExample(unittest.TestCase):
    """Test that the simple hierarchy executes as expected.

    Comparison is done via the text log, so that divergences can easily be checked.
    """
    textlog_align = textlog.Align(cpu=1, time=3, module=7, thread=9)

    @staticmethod
    def _get_kernel(name):
        """Load the kernel module from `name`."""
        # we use importlib so that modules are always reloaded
        spec = importlib.util.find_spec('example.' + name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.KERNEL.module

    def exec_world(self, log, *world_args, **world_kwargs):
        """Create and run a world and test the produced log against a reference."""
        text_buf = io.StringIO()
        text_log = textlog.TextLog(text_buf, self.textlog_align, time_precision=16)

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
        self.exec_world('local_timer_scheduling.log', 1, self._get_kernel('localtimer_kernel'),
                        local_timer_scheduling=True)

    def test_singletimer(self):
        """Test that the single timer hierarchy executes as expected."""
        self.exec_world('single_timer_scheduling.log', 1, self._get_kernel('singletimer_kernel'),
                        local_timer_scheduling=False)

    def test_penalty_scheduler(self):
        """Test that the penalty scheduler executes as expected."""
        self.exec_world('penalty_scheduling.log', 1, self._get_kernel('penalty_scheduler'),
                        local_timer_scheduling=False)

    def test_maximizing_scheduler(self):
        """Test that the maximizing scheduler executes as expected."""
        self.exec_world('maximizing_scheduling.log', 1, self._get_kernel('maximizing_scheduler'),
                        local_timer_scheduling=False)

    def test_cfs(self):
        """Test that the penalty scheduler executes as expected."""
        self.exec_world('cfs_scheduling.log', 1, self._get_kernel('cfs'),
                        local_timer_scheduling=True)

    def test_localtimer_penalty_cfs(self):
        """Test that the penalty CFS executes as expected with local timers."""
        self.exec_world('penalty_cfs_local_timer_scheduling.log', 1,
                        self._get_kernel('penalty_cfs'), local_timer_scheduling=True)

    def test_singletimer_penalty_cfs(self):
        """Test that the penalty CFS executes as expected without local timers."""
        self.exec_world('penalty_cfs_single_timer_scheduling.log', 1,
                        self._get_kernel('penalty_cfs'), local_timer_scheduling=False)


if __name__ == '__main__':
    unittest.main()
