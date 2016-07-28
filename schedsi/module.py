#!/usr/bin/env python3
"""Defines Module."""

from schedsi import threads

class Module: # pylint: disable=too-few-public-methods
    """Module.

    A module has
        * a unique name
        * a parent (or None if kernel)
        * a scheduler
    """

    def __init__(self, name, parent, scheduler):
        """Create a Module."""
        self.name = name
        self.parent = parent
        self.scheduler = threads.SchedulerThread(self, 0, 0, scheduler)
        self.threads = []

    def schedule(self, cpu, current_time, timer_quantum, log):
        """Run the scheduler.

        Returns the remaining timeslice is returned.
        """
        return self.scheduler.execute(cpu, current_time, timer_quantum, log)
