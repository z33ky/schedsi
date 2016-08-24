#!/usr/bin/env python3
"""Defines Module."""

from schedsi import threads

class Module:
    """Module.

    A module has
        * a unique name
        * a parent (or None if kernel)
        * a scheduler thread
        * an array of VCPUs
    """

    def __init__(self, name, parent, scheduler):
        """Create a Module."""
        self.name = name
        self.parent = parent
        self._scheduler_thread = threads.SchedulerThread(0, scheduler(self))
        self._vcpus = []

    def schedule(self, cpu):
        """Run the scheduler.

        Returns the remaining timeslice is returned.
        """
        return self._scheduler_thread.execute(cpu)

    def register_vcpu(self, vcpu):
        """Register a VCPU.

        This is called when a parent adds a VCPUThread
        to schedule this module.

        Returns the scheduler thread.
        """
        if not isinstance(vcpu, threads.VCPUThread):
            print(self.name, "expected a VCPU, got", type(vcpu).__name__, ".")
        self._vcpus.append(vcpu)
        return self._scheduler_thread

    def add_threads(self, new_threads):
        """Add threads."""
        self._scheduler_thread.add_threads(new_threads)
        for vcpu in self._vcpus:
            vcpu.update_child_state()
