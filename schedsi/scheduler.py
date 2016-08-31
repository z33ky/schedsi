#!/usr/bin/env python3
"""Defines the base class for schedulers."""

class Scheduler:
    """Scheduler.

    Has a :obj:`list` of :class:`Threads <schedsi.threads.Thread>`.
    """

    def __init__(self, module):
        """Create a :class:`Scheduler`."""
        self._threads = []
        self._finished_threads = []
        self.module = module

    def add_threads(self, new_threads):
        """Add threads to schedule."""
        self._threads += (t for t in new_threads if t.remaining != 0)
        self._finished_threads += (t for t in new_threads if t.remaining == 0)

    def _get_ready_threads(self, cpu):
        """Return a list of (thread, index) tuples that are ready for execution."""
        assert not False in (t.remaining != 0 for t in self._threads)
        return ((t, i) for i, t in enumerate(self._threads)
                if t.ready_time <= cpu.status.current_time)

    def next_ready_time(self):
        """Find the earliest :attr:`Thread.ready_time` of the
        contained :class:`Threads <schedsi.threads.Thread>`."""
        active_ready_times = list(filter(lambda t: t >= 0,
                                         map(lambda t: t.ready_time, self._threads)))
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
        num_threads = len(self._threads)
        if num_threads <= 1:
            return self._run_thread(next(self._get_ready_threads(cpu), [None])[0], cpu)[0]
        raise RuntimeError('Scheduler cannot make scheduling decision.')

    def _run_thread(self, thread, cpu):
        """Run a :class:`Thread <schedsi.threads.Thread>`.

        The time spent executing and a bool indicating the thread has finished is returned.
        Note that finished threads are moved from :attr:`_threads` to :attr:`_finished_threads`.
        """
        if thread is None:
            cpu.yield_module(self.module)
            return 0, False
        assert thread.ready_time != -1 and thread.ready_time <= cpu.status.current_time
        assert thread in self._threads

        run_time = cpu.switch_thread(thread) + thread.execute(cpu)

        remove = thread.remaining == 0
        if remove:
            self._finished_threads.append(thread)
            self._threads.remove(thread)

        return run_time, remove
