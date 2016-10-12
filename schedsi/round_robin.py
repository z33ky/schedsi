#!/usr/bin/env python3
"""Defines a preemptible Round Robin scheduler."""

from schedsi import scheduler

class RoundRobin(scheduler.Scheduler):
    """RoundRobin scheduler."""

    def __init__(self, module):
        """Create a :class:`RoundRobin` scheduler."""
        super().__init__(module)

    @staticmethod
    def _sched_loop(rcu_copy, last_thread_queue, last_thread_idx):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        See :meth:`Scheduler.schedule() <schedsi.scheduler.Scheduler._sched_loop>`.
        """
        rcu_data = rcu_copy.data
        num_threads = len(rcu_data.ready_threads)
        if num_threads == 0:
            idx = -1
        else:
            idx = last_thread_idx
            if last_thread_queue is rcu_data.ready_threads:
                idx = (idx + 1) % num_threads
            elif last_thread_queue is None or idx == num_threads:
                idx = 0

        rcu_data.rr_idx = idx

        return idx
        #needs to be a coroutine
        yield # pylint: disable=unreachable
