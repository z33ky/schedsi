#!/usr/bin/env python3
"""Defines a Completely Fair Scheduler.

The design is influenced by Linux's CFS scheduler.
"""

import bisect
from schedsi import scheduler


class CFSData(scheduler.SchedulerData):  # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`CFS` scheduler."""

    def __init__(self):
        """Create a :class:`CFSData`."""
        super().__init__()

        self.vruntimes = {}
        self.min_vruntime = None
        self.shares = {}
        # threads may have moved in the queues after _start_schedule()
        # these are the new indices
        self.waiting_idx = None
        self.ready_idx = None


class CFS(scheduler.Scheduler):
    """Completely Fair Scheduler.

    Both CFSData.ready_chains and CFSData.waiting_chains
    are sorted by their vruntime.

    This scheduler uses time-slices and can thus not be used outside
    the kernel with the single timer scheduling strategy.
    Use the :class:`PenaltySchedulerAddon` or the
    :class:`FixedTimeSliceSchedulerAddon` for this case.
    """

    def __init__(self, module, *, default_shares, min_period, min_slice, **kwargs):
        """Create a :class:`CFS` scheduler.

        `default_shares` is also used to scale a vruntime.
        CFS tries to limit how far vruntimes drift apart, so long-running
        threads may receive smaller time slices with larger vruntime scales.
        If `default_shares` is 0, `shares` for :meth:`add_thread` has to be specified
        for every thread.
        `min_period` corresponds to "sched_min_latency" of Linux CFS.
        `min_slice` corresponds to "sched_min_granularity" of Linux CFS.
        """
        super().__init__(module, CFSData(), **kwargs)
        assert default_shares >= 0
        self.default_shares = default_shares
        assert min_period > 0
        self.min_period = min_period
        assert min_slice >= 0
        self.min_slice = min_slice

    def add_thread(self, thread, rcu_data=None, *, shares=None):
        """See :meth:`Scheduler.add_thread`."""
        if shares is None:
            shares = self.default_shares
        assert shares > 0

        super_add_thread = super().add_thread

        def appliance(data):
            """Append new threads to the waiting and finished queue."""
            assert thread not in data.vruntimes
            assert thread not in data.shares

            super_add_thread(thread, data)

            data.vruntimes[thread] = None
            data.shares[thread] = shares

        if rcu_data is None:
            self._rcu.apply(appliance)
        else:
            appliance(rcu_data)

    def _get_vruntime_fact(self, thread, rcu_data):
        """Get factor for the `thread`'s vruntime."""
        return self.default_shares / rcu_data.shares[thread]

    def _get_last_chain(self, rcu_data, last_queue, _last_idx):
        """See :meth:`Scheduler._get_last_chain`."""
        if last_queue is rcu_data.ready_chains:
            return rcu_data.ready_chains[rcu_data.ready_idx]
        if last_queue is rcu_data.waiting_chains:
            return rcu_data.waiting_chains[rcu_data.waiting_idx]
        if last_queue is rcu_data.finished_chains:
            return rcu_data.finished_chains[-1]
        assert last_queue is None
        return None

    def _start_schedule(self, prev_run_time):
        """See :meth:`Scheduler._start_schedule`."""
        rcu_copy, last_queue, last_idx = yield from super()._start_schedule(prev_run_time)
        rcu_data = rcu_copy.data

        rcu_data.ready_idx = last_idx
        # we didn't move the chain yet, so it's at the end of the queue
        rcu_data.waiting_idx = -1
        update_min_vruntime = False

        last_chain = self._get_last_chain(rcu_data, last_queue, last_idx)
        if last_chain is not None:
            assert prev_run_time is not None
            # TODO: if last_queue is rcu_data.finished_chains: del ...

            # update vruntime
            thread = last_chain.bottom
            weighted_run_time = prev_run_time * self._get_vruntime_fact(thread, rcu_data)
            rcu_data.vruntimes[thread] += weighted_run_time

            # check if we need to update min_vruntime
            update_min_vruntime = rcu_data.min_vruntime < rcu_data.vruntimes[thread]

        if last_queue is rcu_data.waiting_chains:
            assert prev_run_time is not None
            rcu_data.waiting_idx = self._update_waiting(rcu_data.waiting_chains,
                                                        rcu_data.vruntimes, rcu_data.min_vruntime)
        else:
            rcu_data.waiting_idx = None

        if update_min_vruntime:
            rcu_data.min_vruntime = self._calc_min_vruntime(rcu_data.ready_chains,
                                                            rcu_data.vruntimes)

        if last_queue is rcu_data.ready_chains:
            assert last_idx == 0
            rcu_data.ready_idx = self._update_ready(rcu_data.ready_chains, rcu_data.vruntimes)
        else:
            rcu_data.ready_idx = None

        assert rcu_data.ready_idx is None or rcu_data.waiting_idx is None

        return rcu_copy, last_queue, last_idx

    @staticmethod
    def _calc_min_vruntime(ready_chains, vruntimes):
        """Calculate the minimal vruntime.

        Should be called from :meth:`_start_schedule`,
        after :meth:`_update_waiting` and before :meth:`_update_ready`.
        """
        # check first thread
        try:
            thread = ready_chains[0].bottom
        except IndexError:
            # no threads, no min_vruntime
            return None
        min_vruntime = vruntimes[thread]

        # check second thread
        try:
            thread = ready_chains[1].bottom
        except IndexError:
            return
        return min(min_vruntime, vruntimes[thread])

    @staticmethod
    def _update_waiting(waiting_chains, runtimes, min_runtime):
        """`waiting_chains` maintenance.

        Should be called from :meth:`_start_schedule` if the previously executed thread
        is now waiting.

        Returns the index of the previously executed thread in `waiting_chains`.
        """
        # sorted reinsertion
        chain = waiting_chains.pop()
        runtimes[chain.bottom] -= min_runtime
        runtime = runtimes[chain.bottom]

        # treat None as a value bigger than runtime for bisection
        idx = bisect.bisect([runtimes[c.bottom] or runtime + 1 for c in waiting_chains], runtime)

        waiting_chains[idx:idx] = [chain]

        return idx

    @staticmethod
    def _update_ready(ready_chains, runtimes):
        """`ready_chains` maintenance.

        Should be called from :meth:`_start_schedule` if the previously executed thread
        is still ready to be executed.

        Returns the index of the previously executed thread in `ready_chains`.
        """
        chain = ready_chains.pop(0)
        idx = bisect.bisect([runtimes[c.bottom] for c in ready_chains], runtimes[chain.bottom])
        if idx == 0:
            # force reschedule
            idx = 1
        ready_chains[idx:idx] = [chain]
        return idx

    def _update_ready_chains(self, time, rcu_data):
        """See :meth:`Scheduler._update_ready_chains`."""
        ready_chains = rcu_data.ready_chains
        new_idx = len(ready_chains)
        super()._update_ready_chains(time, rcu_data)
        new_chains = ready_chains[new_idx:]
        del ready_chains[new_idx:]

        if rcu_data.min_vruntime is None:
            rcu_data.min_vruntime = time

        for chain in new_chains:
            if rcu_data.vruntimes[chain.bottom] is None:
                # FIXME: subtract ((time - ready_time) * _get_vruntime_fact()) from vruntime
                rcu_data.vruntimes[chain.bottom] = 0
            rcu_data.vruntimes[chain.bottom] += rcu_data.min_vruntime

        # figure out insertion point
        idx = next((i for i, c in enumerate(rcu_data.ready_chains)
                    if rcu_data.vruntimes[c.bottom] > rcu_data.min_vruntime), 0)
        if idx == 0 and rcu_data.last_idx == 0:
            # the ready_chains[0] is executing, so we need to insert past it
            idx = 1

        ready_chains[idx:idx] = new_chains

    @staticmethod
    def _get_ratio(thread, rcu_data):
        """Calculate the share ratio of a thread."""
        return rcu_data.shares[thread] / sum(rcu_data.shares[c.bottom]
                                             for c in rcu_data.ready_chains)

    def _get_slice(self, thread, rcu_data):
        """Calculate the slice for the thread."""
        period = max(len(rcu_data.ready_chains) * self.min_slice, self.min_period)
        return period * self._get_ratio(thread, rcu_data)

    def _sched_loop(self, rcu_copy, last_thread_queue, last_thread_idx):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        See :meth:`Scheduler.schedule() <schedsi.scheduler.Scheduler._sched_loop>`.
        """
        rcu_data = rcu_copy.data

        if last_thread_queue is rcu_data.ready_chains:
            assert last_thread_idx == 0
            if len(rcu_data.ready_chains) == 1:
                thread = rcu_data.ready_chains[0].bottom
                return 0, max(self._get_slice(thread, rcu_data), self.min_slice)

        if not rcu_data.ready_chains:
            return -1, None

        thread = rcu_data.ready_chains[0].bottom
        time_slice = self._get_slice(thread, rcu_data)

        # don't let vruntimes differ more than the time slice
        try:
            next_thread = rcu_data.ready_chains[1].bottom
        except IndexError:
            pass
        else:
            vruntime_fact = self._get_vruntime_fact(thread, rcu_data)
            vdelta = time_slice * vruntime_fact
            future_vruntime = rcu_data.vruntimes[thread] + vdelta
            future_vdelta = future_vruntime - rcu_data.vruntimes[next_thread]
            if future_vdelta > time_slice:
                time_slice -= (vdelta - time_slice) / vruntime_fact

        return 0, max(time_slice, self.min_slice)
        # needs to be a coroutine
        yield  # pylint: disable=unreachable
