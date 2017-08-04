#!/usr/bin/env python3
"""Defines the :class:`InterpreterError`."""

class InterpreterError(RuntimeError):
    """This class represents errors occurring while interpreting schedsim expressions."""
    def __init__(self, msg, node=None):
        super().__init__(msg, node)
        self.msg = msg
        self.node = node
