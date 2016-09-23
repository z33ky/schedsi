#!/usr/bin/env python3
"""Defines :class:`Module`."""

import sys
from schedsi import cpu, threads

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
        #HACK: VCPUs are usually added after other threads, but we need it sooner
        #      to get a num_threads count for naming threads.
        #      In particular, this is a problem for Cores, which are added in World.
        self._vcpus = [(None, self._scheduler_thread)]
        self._children = []
        if not parent is None:
            parent.register_child(self)

    def register_vcpu(self, vcpu):
        """Register a VCPU.

        This is called when a parent adds a :class:`VCPUThread <schedsi.threads.VCPUThread>`
        to schedule this module.

        Returns the scheduler thread.
        """
        #HACK: see __init__ for self._vcpus
        if self._vcpus == [(None, self._scheduler_thread)]:
            self._vcpus = []
        if len(self._vcpus) == 1:
            raise RuntimeError("Does not support more than 1 vcpu yet.")
        if not isinstance(vcpu, (threads.VCPUThread, cpu.Core)):
            print(self.name, "expected a VCPU, got", type(vcpu).__name__, ".", file=sys.stderr)
        self._vcpus.append((vcpu, self._scheduler_thread))
        return self._scheduler_thread

    def register_child(self, child):
        self._children.append(child)

    def num_threads(self):
        return sum(s[1].num_threads() for s in self._vcpus) + len(self._vcpus)

    def add_threads(self, new_threads):
        """Add threads.

        See :meth:`SchedulerThread.add_threads() <schedsi.threads.SchedulerThread.add_threads>`.
        """
        self._scheduler_thread.add_threads(new_threads)

    def get_thread_statistics(self):
        """Obtain statistics of threads managed by this module."""
        return {(self.name, vcpu[1].tid): vcpu[1].get_statistics() for vcpu in self._vcpus}
