#!/usr/bin/env python3
"""Defines the base class for schedulers."""

class Scheduler:
    """Scheduler.

    Has a list of threads.
    """

    def __init__(self, module):
        """Create a scheduler."""
        self.threads = []
        self.module = module

    def next_start_time(self):
        """Find the nearest start_time of the contained threads."""
        active_thread_start_times = list(filter(lambda t: t >= 0,
                                                map(lambda t: t.start_time, self.threads)))
        if not active_thread_start_times:
            return -1
        return min(active_thread_start_times)

    def schedule(self, cpu):
        """Schedule the next thread.

        This scheduler is a base class.
        This function will only deal with a single thread.
        If more are present, a RuntimeError is raised.

        The remaining timeslice is returned.
        """
        num_threads = len(self.threads)
        if num_threads == 0:
            return self._run_thread(None, cpu)
        if num_threads == 1:
            return self._run_thread(self.threads[0], cpu)
        raise RuntimeError('Scheduler cannot make scheduling decision.')

    def _run_thread(self, thread, cpu):
        """Run a thread.

        The time spent executing is returned.
        """
        if thread is None:
            cpu.yield_module(self.module)
            return 0
        return cpu.switch_thread(thread) + thread.execute(cpu)
