#!/usr/bin/env python3
"""Defines a multilevel feedback queue scheduler with per-queue time-slices.

With penalties we can prevent gaming of the scheduler as described in
`multilevel_feedback_queue.py`.

On top of just using the :class:`PenaltySchedulerAddon`, with :class:`PenaltyMLFQ`
a different time-slice for each priority can be defined.
"""

from schedsi import multilevel_feedback_queue, penalty_scheduler_addon, scheduler

class PenaltyMLFQ(scheduler.SchedulerAddon, multilevel_feedback_queue.MLFQ):
    """A :class:`multilevel_feedback_queue` variant with per-queue time-slices."""

    def __init__(self, module, *, timeslices, priority_boost_time=None):
        """Create a :class:`PenaltyMLFQ` scheduler."""
        super().__init__(module, penalty_scheduler_addon.PenaltySchedulerAddon(self, None, 0),
                         levels=len(timeslices), priority_boost_time=priority_boost_time)
        self.timeslices = timeslices

        self.addon.threshold = None
        #we overwrite self.addon.schedule in _schedule
        self.addon_schedule = self.addon.schedule
        #this is just to make sure we do overwrite it before it's called
        self.addon.schedule = None

    def _start_schedule(self, prev_run_time):
        """See :meth:`Scheduler._start_schedule`."""
        #this is just to make sure we do overwrite it before it's called
        self.addon.schedule = None
        return (yield from super()._start_schedule(prev_run_time))

    def _schedule(self, idx, rcu_copy):
        """See :meth:`Scheduler._schedule`."""
        queue_idx = next(i for i, v in enumerate(rcu_copy.data.ready_queues)
                         if v is rcu_copy.data.ready_chains)

        timeslice = self.timeslices[queue_idx]
        threshold = -timeslice / 2

        self.addon.schedule = lambda *args: self.addon_schedule(*args, timeslice, threshold)

        yield from super()._schedule(idx, rcu_copy)
