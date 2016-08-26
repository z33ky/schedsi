#!/usr/bin/env python3
"""Defines a Round Robin scheduler."""

from schedsi import scheduler

class RoundRobin(scheduler.Scheduler):
    """RoundRobin scheduler."""

    def __init__(self, module):
        """Create a RoundRobin scheduler."""
        super().__init__(module)
        self._next_idx = 0

    def schedule(self, cpu):
        """Schedule the next thread.

        The remaining timeslice is returned.
        """
        num_threads = len(self.threads)

        if num_threads == 0:
            return self._run_thread(None, cpu)

        thread = None
        idx = self._next_idx
        last_idx = idx - 1 if idx != 0 else num_threads - 1
        while True:
            thread = self.threads[idx]
            if thread.start_time >= 0 and thread.start_time <= cpu.status.current_time:
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
