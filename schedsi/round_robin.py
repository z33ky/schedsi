#!/usr/bin/env python3
"""Defines a preemptible Round Robin scheduler."""

from schedsi import scheduler

class RoundRobinData(scheduler.SchedulerData): # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`RoundRobin` scheduler."""
    def __init__(self):
        """Create a :class:`RoundRobinData`."""
        super().__init__()
        self.rr_idx = -1

class RoundRobin(scheduler.Scheduler):
    """RoundRobin scheduler."""

    def __init__(self, module):
        """Create a :class:`RoundRobin` scheduler."""
        super().__init__(module, RoundRobinData())

    def schedule(self):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        See :meth:`Scheduler.schedule() <schedsi.scheduler.Scheduler.schedule>`.
        """
        while True:
            rcu_copy, removed = yield from self._start_schedule()
            rcu_data = rcu_copy.data
            num_threads = len(rcu_data.ready_threads)
            if num_threads == 0:
                rcu_data.rr_idx = -1
                if not self._rcu.update(rcu_copy):
                    #yield 1
                    continue
                yield 0
                return

            idx = rcu_data.rr_idx
            if not removed:
                idx = (idx + 1) % num_threads
            elif idx == num_threads:
                idx = 0

            rcu_data.rr_idx = idx

            yield from self._schedule(idx, rcu_copy)
