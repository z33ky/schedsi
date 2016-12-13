#!/usr/bin/env python3
"""Test that the example works."""

import subprocess
import unittest


class TestExample(unittest.TestCase):
    """Test that the example works."""

    def test_example(self):  # pylint: disable=no-self-use
        """Test that the example works."""
        subprocess.run(['example/kernel.py', '-'], stdout=subprocess.DEVNULL, check=True)


if __name__ == '__main__':
    unittest.main()
