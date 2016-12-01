#!/usr/bin/env python3
"""Defines a :class:`Context` and :class:`Chain` thereof."""

class Context:
    """An operation context for a CPU Core.

    The context has
        * the current :class:`Thread`
        * the execution coroutine of the :class:`Thread`
    """

    def __init__(self, thread):
        """Create a :class:`Context`"""
        self.thread = thread
        self.execution = thread.execute()
        self.started = False

    def execute(self, current_time):
        """Run the execution coroutine."""
        if self.started:
            return self.execution.send(current_time)
        else:
            self.started = True
            return next(self.execution)

    def restart(self, current_time):
        """Restart the thread.

        Calls :meth:`Thread.finish()` and then starts a new coroutine.
        """
        assert self.started
        self.thread.finish(current_time)
        self.execution = self.thread.execute()
        self.started = False
