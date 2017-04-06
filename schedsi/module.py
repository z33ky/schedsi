#!/usr/bin/env python3
"""Defines :class:`Module`."""

import sys
from schedsi.cpu import core
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
        self._scheduler_thread = threads.SchedulerThread("scheduler", scheduler=scheduler(self))
        self._vcpus = []
        self._children = []
        if parent is not None:
            parent.attach_module(self)

    def register_vcpu(self, vcpu):
        """Register a VCPU.

        This is called when a parent adds a :class:`~schedsi.threads.VCPUThread`
        to schedule this module.

        Returns the scheduler thread.
        """
        if len(self._vcpus) == 1:
            raise RuntimeError('Does not support more than 1 vcpu yet.')
        if not isinstance(vcpu, (threads.VCPUThread, core.Core)):
            print(self.name, 'expected a VCPU, got', type(vcpu).__name__, '.', file=sys.stderr)
        self._vcpus.append((vcpu, self._scheduler_thread))
        return self._scheduler_thread

    def attach_module(self, child):
        """Attach a child module."""
        assert isinstance(child, Module)
        self._children.append(child)

    def num_children(self):
        """Return the number of children."""
        return len(self._children)

    def num_work_threads(self):
        """Return number of work threads managed by this module."""
        #FIXME: this includes VCPU threads
        return self._scheduler_thread.num_threads()

    def add_thread(self, thread, **kwargs):
        """Add threads.

        See :meth:`SchedulerThread.add_threads() <schedsi.threads.SchedulerThread.add_threads>`.
        """
        self._scheduler_thread.add_thread(thread, **kwargs)

    def all_threads(self):
        """Return a generator yielding every thread."""
        return self._scheduler_thread.all_threads()

    def get_thread_statistics(self, current_time):
        """Obtain statistics of threads managed by this module."""
        return {(self.name, vcpu[1].tid): vcpu[1].get_statistics(current_time)
                for vcpu in self._vcpus}
