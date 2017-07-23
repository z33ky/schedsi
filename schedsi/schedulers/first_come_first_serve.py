#!/usr/bin/env python3
"""Defines a first come first serve scheduler."""

from schedsi.schedulers import scheduler


class FCFS(scheduler.Scheduler):
    """First come first serve scheduler."""

    def __init__(self, module, *, time_slice=None, **kwargs):
        """Create a :class:`SJF` scheduler."""
        if time_slice is not None:
            raise RuntimeError('FCFS does not use a time-slice.')
        super().__init__(module, **kwargs)

    def _sched_loop(self, rcu_copy):
        """Schedule the next :class:`~schedsi.threads.Thread`.

        See :meth:`~schedsi.scheduler.Scheduler._sched_loop`.
        """
        idx = 0
        if not rcu_copy.data.ready_chains:
            idx = -1
        return idx, self.time_slice
        # needs to be a coroutine
        yield  # pylint: disable=unreachable
