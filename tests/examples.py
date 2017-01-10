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
        """Test that the local-timer example works."""
        self.example('localtimer_kernel')

    def test_singletimer(self):  # pylint: disable=no-self-use
        """Test that the single-timer example works."""
        self.example('singletimer_kernel')


if __name__ == '__main__':
    unittest.main()