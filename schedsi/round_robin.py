#!/usr/bin/env python3
"""Defines a preemptible Round Robin scheduler."""

from schedsi import scheduler

class RoundRobin(scheduler.Scheduler):
    """RoundRobin scheduler."""

    def __init__(self, module):
        """Create a :class:`RoundRobin` scheduler."""
        super().__init__(module)
        self._next_idx = 0

    def schedule(self, cpu):
        """Run the next :class:`Thread <schedsi.threads.Thread>`.

        See :meth:`Scheduler.schedule() <schedsi.scheduler.Scheduler.schedule>`.
        """
        num_threads = len(self._threads)

        if num_threads == 0:
            return self._run_thread(None, cpu)

        thread = None
        idx = self._next_idx
        last_idx = idx - 1 if idx != 0 else num_threads - 1
        while True:
            thread = self._threads[idx]
            if thread.ready_time >= 0 and thread.ready_time <= cpu.status.current_time:
                break
            if idx == last_idx:
                #tried all threads, but no thread ready
                cpu.yield_module(self.module)
                return 0

            idx = idx + 1 if idx != num_threads - 1 else 0

        self._next_idx = idx + 1 if idx != num_threads - 1 else 0

        run_time = self._run_thread(thread, cpu)
        if cpu.status.pending_interrupt or run_time == 0:
            return 0

        return run_time + self.schedule(cpu)
