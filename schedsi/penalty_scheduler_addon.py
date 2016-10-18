#!/usr/bin/env python3
"""Defines a base class for schedulers attempting to run
threads for certain timeslices.

Without a local timer, this is approximated by keeping track
of the difference of the debit and credit ("penalty").
"""

from schedsi import scheduler

class PenaltySchedulerAddonData(): # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`PenaltySchedulerAddon`."""

    def __init__(self):
        """Create a :class:`PenaltySchedulerAddonData`."""
        self.sat_out_thread = None
        self.penalties = {}

class PenaltySchedulerAddon(scheduler.SchedulerAddonBase):
    """Penalty tracking scheduler-addon.

    :attr:`penalty` is always <= 0 and represents how much longer
    the thread ran than the timeslice specified.
    When a thread's :attr:`penalty` exceeds the :attr:`threshold`
    and is selected by the scheduler, the thread with the lowest
    :attr:`penalty` will be run instead.
    """

    def __init__(self, addee, timeslice, threshold=None):
        """Create a :class:`PenaltySchedulerAddon`."""
        super().__init__(addee)
        self.timeslice = timeslice
        if threshold is None:
            #is this a reasonable default?
            #is there a reasonable default?
            threshold = -timeslice / 2
        self.threshold = threshold

    def transmute_rcu_data(self, original, *addon_data): # pylint: disable=no-self-use
        """See :meth:`SchedulerAddonBase.transmute_rcu_data`."""
        super().transmute_rcu_data(original, PenaltySchedulerAddonData, *addon_data)

    def start_schedule(self, prev_run_time, rcu_data, last_thread_queue, last_thread_idx):
        """See :meth:`SchedulerAddonBase.start_schedule`."""
        super().start_schedule(prev_run_time, rcu_data, last_thread_queue, last_thread_idx)
        last_thread = self._get_last_thread(rcu_data, last_thread_queue, last_thread_idx)

        penalty = 0
        if not last_thread is None:
            if last_thread.remaining == 0:
                del rcu_data.penalties[last_thread]
            else:
                rcu_data.penalties[last_thread] -= prev_run_time
                penalty = rcu_data.penalties[last_thread]

        if rcu_data.sat_out_thread:
            assert last_thread and not last_thread is rcu_data.sat_out_thread
            rcu_data.penalties[rcu_data.sat_out_thread] += prev_run_time
            penalty = max(penalty, rcu_data.penalties[rcu_data.sat_out_thread])
            rcu_data.sat_out_thread = None

        if penalty > 0:
            #shift back to 0
            for k in rcu_data.penalties:
                rcu_data.penalties[k] -= penalty

    #this differs only in optional arguments
    def schedule(self, idx, rcu_data, timeslice=None): # pylint: disable=arguments-differ
        """Proxy for a :meth:`_schedule <schedsi.scheduler.Scheduler._schedule>` call.

        Checks the penalty for the selected thread and may return a different index to choose
        with the lowest penalty.
        """
        if idx == -1:
            assert not rcu_data.ready_threads
            return -1

        if not timeslice:
            timeslice = self.timeslice

        thread = rcu_data.ready_threads[idx]

        penalty = rcu_data.penalties.setdefault(thread, 0)
        if penalty < self.threshold:
            rcu_data.sat_out_thread = thread
            idx = max(range(0, len(rcu_data.ready_threads)),
                      key=lambda i: rcu_data.penalties.get(rcu_data.ready_threads[i], 0))
            thread = rcu_data.ready_threads[idx]
            if rcu_data.sat_out_thread is thread:
                rcu_data.sat_out_thread = None

        rcu_data.penalties[thread] += timeslice

        return super().schedule(idx, rcu_data)
