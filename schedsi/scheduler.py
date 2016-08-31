#!/usr/bin/env python3
"""Defines the base class for schedulers."""

class Scheduler:
    """Scheduler.

    Has a :obj:`list` of :class:`Threads <schedsi.threads.Thread>`.
    """

    def __init__(self, module):
        """Create a :class:`Scheduler`."""
        self.threads = []
        self.module = module

    def next_ready_time(self):
        """Find the earliest :attr:`Thread.ready_time` of the
        contained :class:`Threads <schedsi.threads.Thread>`."""
        active_ready_times = list(filter(lambda t: t >= 0,
                                         map(lambda t: t.ready_time, self.threads)))
        if not active_ready_times:
            return -1
        return min(active_ready_times)

    def schedule(self, cpu):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        This :class:`Scheduler` is a base class.
        This function will only deal with a single :class:`Thread <schedsi.threads.Thread>`.
        If more are present, a :exc:`RuntimeError` is raised.

        The time spent executing is returned.
        """
        num_threads = len(self.threads)
        if num_threads == 0:
            return self._run_thread(None, cpu)
        if num_threads == 1:
            return self._run_thread(self.threads[0], cpu)
        raise RuntimeError('Scheduler cannot make scheduling decision.')

    def _run_thread(self, thread, cpu):
        """Run a :class:`Thread <schedsi.threads.Thread>`.

        The time spent executing is returned.
        """
        if thread is None:
            cpu.yield_module(self.module)
            return 0
        return cpu.switch_thread(thread) + thread.execute(cpu)
