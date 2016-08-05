#!/usr/bin/env python3
"""Test that the example works."""

import subprocess
import unittest

class TestExample(unittest.TestCase):
    """Test that the example works."""

    def test_example(self):
        """Test that the example works."""
        self.assertEqual(subprocess.check_call(["example/kernel.py", "-"]), 0)

if __name__ == '__main__':
    unittest.main()
