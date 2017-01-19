#!/usr/bin/env python3
"""Defines a base class for schedulers attempting to run threads for certain time-slices.

Without a local timer, this is approximated by keeping track of the difference of the debit
and credit ("niceness").
"""

from schedsi import scheduler


class PenaltySchedulerAddonData():  # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`PenaltySchedulerAddon`."""

    def __init__(self):
        """Create a :class:`PenaltySchedulerAddonData`."""
        self.sat_out_threads = []
        self.last_time_slice = None
        self.niceness = {}


class PenaltySchedulerAddon(scheduler.SchedulerAddonBase):
    """Penalty tracking scheduler-addon.

    `niceness` is always <= 0 and represents how much longer the chain ran
    than the time-slice specified.  When a chain's `niceness` falls behind
    the :attr:`threshold` and is selected by the scheduler, it is blocked
    and the scheduler gets rerun until it either repeats a decision or
    selects a chain that has a `niceness` above the :attr:`threshold`.
    """

    def __init__(self, *args, penalty_time_slice, threshold=None):
        """Create a :class:`PenaltySchedulerAddon`."""
        super().__init__(*args)
        self.penalty_time_slice = penalty_time_slice
        if threshold is None:
            # is this a reasonable default?
            # is there a reasonable default?
            threshold = -penalty_time_slice / 2
        self.threshold = threshold

    def transmute_rcu_data(self, original, *addon_data):  # pylint: disable=no-self-use
        """See :meth:`SchedulerAddonBase.transmute_rcu_data`."""
        super().transmute_rcu_data(original, PenaltySchedulerAddonData, *addon_data)

    def start_schedule(self, prev_run_time, rcu_data, last_chain_queue, last_chain_idx):
        """See :meth:`SchedulerAddonBase.start_schedule`."""
        super().start_schedule(prev_run_time, rcu_data, last_chain_queue, last_chain_idx)
        last_chain = self._get_last_chain(rcu_data, last_chain_queue, last_chain_idx)
        last_thread = last_chain and last_chain.bottom
        last_id = id(last_thread)

        niceness = 0
        if last_chain is not None and last_id not in rcu_data.sat_out_threads:
            if last_thread.is_finished():
                niceness = rcu_data.niceness.pop(last_id)
                if niceness >= 0 and rcu_data.niceness:
                    niceness = max(rcu_data.niceness.values())
                else:
                    niceness = 0
            else:
                if prev_run_time == 0:
                    # probably was blocked by another addon
                    rcu_data.sat_out_threads.append(last_id)
                else:
                    rcu_data.niceness[last_id] += rcu_data.last_time_slice - prev_run_time
                    niceness = rcu_data.niceness[last_id]
                rcu_data.last_time_slice = None

        if rcu_data.sat_out_threads:
            assert last_chain
            if not last_id == rcu_data.sat_out_threads[-1]:
                assert prev_run_time > 0
                for tid in rcu_data.sat_out_threads:
                    rcu_data.niceness[tid] += prev_run_time
                    niceness = max(niceness, rcu_data.niceness[tid])
                rcu_data.sat_out_threads.clear()

        if niceness > 0 or \
           niceness < 0 and max(rcu_data.niceness.values()) == niceness:
            # shift back to 0
            for k in rcu_data.niceness.keys():
                rcu_data.niceness[k] -= niceness
        assert not rcu_data.niceness or 0 in rcu_data.niceness.values()

    # this differs only in optional arguments
    def schedule(self, idx, rcu_data, time_slice=None, threshold=None):  # pylint: disable=arguments-differ
        """See :meth:`SchedulerAddonBase.schedule`.

        Checks the niceness for the selected chain and blocks it
        if it's below the :attr:`threshold`.
        """
        if idx == -1:
            return True

        if not time_slice:
            time_slice = self.penalty_time_slice
        assert time_slice

        if not threshold:
            threshold = self.threshold
        assert threshold

        tid = id(rcu_data.ready_chains[idx].bottom)

        niceness = rcu_data.niceness.setdefault(tid, 0)
        if niceness < threshold:
            if tid in rcu_data.sat_out_threads:
                # scheduler selected a thread that we wanted to stall again
                # allow it to run then
                # TODO: retry & count retries to self.max_retries
                rcu_data.sat_out_threads.clear()
            else:
                # only nicest thread may run
                nicest_tid = max((id(c.bottom) for c in rcu_data.ready_chains),
                                 key=lambda tid: rcu_data.niceness.get(tid, 0))
                assert niceness <= rcu_data.niceness[nicest_tid]
                if tid != nicest_tid:
                    rcu_data.sat_out_threads.append(tid)
                    rcu_data.last_timeslice = None
                    return False

        rcu_data.last_time_slice = time_slice

        return True
