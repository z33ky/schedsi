#!/usr/bin/env python3
"""Defines a Round Robin scheduler."""

from schedsi import scheduler

class RoundRobin(scheduler.Scheduler):
    """RoundRobin scheduler."""

    def __init__(self, module):
        """Create a RoundRobin scheduler."""
        super().__init__(module)
        self._next_idx = 0

    def schedule(self, cpu, current_time, run_time, log):
        """Schedule the next thread.

        The remaining timeslice is returned.
        """
        num_threads = len(self.threads)

        if num_threads == 0:
            return self._run_thread(None, cpu, current_time, run_time, log)

        thread = None
        idx = self._next_idx
        last_idx = idx - 1 if idx != 0 else num_threads - 1
        while True:
            thread = self.threads[idx]
            if thread.start_time >= 0 and thread.start_time <= current_time:
                break
            if idx == last_idx:
                #tried all threads, but no thread ready
                log.schedule_none(cpu, current_time, self.module)
                return run_time

            idx = idx + 1 if idx != num_threads - 1 else 0

        self._next_idx = idx + 1 if idx != num_threads - 1 else 0

        left = self._run_thread(thread, cpu, current_time, run_time, log)
        if left == 0:
            return 0

        current_time += run_time - left

        return self.schedule(cpu, current_time, left, log)
