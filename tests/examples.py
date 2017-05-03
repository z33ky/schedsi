#!/usr/bin/env python3
"""Test that the example works."""

import subprocess
import unittest


class TestExample(unittest.TestCase):
    """Test that the example works."""

    @staticmethod
    def example(basename):
        """Test that the example works."""
        subprocess.run(['example/' + basename + '.py', '-'], stdout=subprocess.DEVNULL, check=True)

    def test_localtimer(self):  # pylint: disable=no-self-use
        """Test that the local-timer example can run."""
        self.example('localtimer_kernel')

    def test_singletimer(self):  # pylint: disable=no-self-use
        """Test that the single-timer example can run."""
        self.example('singletimer_kernel')

    def test_penalty_scheduler(self):  # pylint: disable=no-self-use
        """Test that the penalty-scheduler example can run."""
        self.example('penalty_scheduler')

    def test_penalty_scheduler(self):  # pylint: disable=no-self-use
        """Test that the penalty-cfs example can run."""
        self.example('penalty_cfs')

    def test_maximizing_scheduler(self):  # pylint: disable=no-self-use
        """Test that the maximizing-scheduler example can run."""
        self.example('maximizing_scheduler')

    def test_cfs(self):  # pylint: disable=no-self-use
        """Test that the cfs example can run."""
        self.example('cfs')

    def test_fixed_cfs(self):  # pylint: disable=no-self-use
        """Test that the fixed-cfs example can run."""
        self.example('fixed_cfs')


if __name__ == '__main__':
    unittest.main()
