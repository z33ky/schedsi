#!/usr/bin/env python3
"""Defines :class:`Module`."""

import sys
from schedsi import threads

class Module:
    """A module is more or less a process.

    A module has
        * a unique name
        * a parent (or None if kernel)
        * a scheduler thread
        * an array of (VCPU, scheduler thread)
    """

    def __init__(self, name, parent, scheduler):
        """Create a :class:`Module`."""
        self.name = name
        self.parent = parent
        self._scheduler_thread = threads.SchedulerThread(0, scheduler=scheduler(self))
        self._vcpus = []

    def register_vcpu(self, vcpu):
        """Register a VCPU.

        This is called when a parent adds a :class:`VCPUThread <schedsi.threads.VCPUThread>`
        to schedule this module.

        Returns the scheduler thread.
        """
        if not isinstance(vcpu, threads.VCPUThread):
            print(self.name, "expected a VCPU, got", type(vcpu).__name__, ".", file=sys.stderr)
        self._vcpus.append(vcpu)
        return self._scheduler_thread

    def add_threads(self, new_threads):
        """Add threads.

        See :meth:`SchedulerThread.add_threads() <schedsi.threads.SchedulerThread.add_threads>`.
        """
        self._scheduler_thread.add_threads(new_threads)
