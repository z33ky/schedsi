#!/usr/bin/env python3
"""Defines a scheduler addon, that penalizes threads running more than their allotted time-slices.

This allows approximation of time-slices without a local timer by recording the difference of
debit and credit ("niceness").
"""

from . import time_slice_fixer


class PenalizerData():  # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`PenalizerAddon`."""

    def __init__(self):
        """Create a :class:`PenalizerData`."""
        self.sat_out_threads = []
        self.last_time_slice = None
        self.niceness = {}


class Penalizer(time_slice_fixer.TimeSliceFixer):
    """Penalty tracking scheduler-addon.

    `niceness` is always <= 0 and represents how much longer the chain ran
    than the time-slice specified.  When a chain's `niceness` falls behind
    the :attr:`threshold` and is selected by the scheduler, it is blocked
    and the scheduler gets rerun until it either repeats a decision or
    selects a chain that has a `niceness` above the :attr:`threshold`.
    """

    def __init__(self, *args, override_time_slice=None, threshold=None):
        """Create a :class:`Penalizer`.

        `threshold` is a function that takes the time-slice to be used
        and returns the amount the niceness values may differ for that
        time-slice.
        """
        super().__init__(*args, override_time_slice=override_time_slice)
        if threshold is None:
            # is this a reasonable default?
            # is there a reasonable default?
            def threshold(time_slice):  # pylint: disable=function-redefined
                """Return the threshold for the `time_slice`."""
                return -time_slice / 2
        self.threshold = threshold

    def transmute_rcu_data(self, original, *addon_data):  # pylint: disable=no-self-use
        """See :meth:`Addon.transmute_rcu_data`."""
        super().transmute_rcu_data(original, PenalizerData, *addon_data)

    def add_thread(self, thread, rcu_data):
        """See :meth:`Addon.add_thread`."""
        assert not thread in rcu_data.niceness
        if not thread.is_finished():
            rcu_data.niceness[id(thread)] = 0

    def start_schedule(self, prev_run_time, rcu_data, last_chain_queue, last_chain_idx):
        """See :meth:`Addon.start_schedule`."""
        super().start_schedule(prev_run_time, rcu_data, last_chain_queue, last_chain_idx)
        if prev_run_time and rcu_data.last_time_slice is None:
            assert not rcu_data.sat_out_threads
            return
        last_chain = self._get_last_chain(rcu_data, last_chain_queue, last_chain_idx)
        last_thread = last_chain and last_chain.bottom
        last_id = id(last_thread)

        niceness = 0
        if last_chain is not None and last_id not in rcu_data.sat_out_threads:
            if last_thread.is_finished():
                last_niceness = rcu_data.niceness.pop(last_id)
                if last_niceness >= 0 and rcu_data.niceness:
                    niceness = max(rcu_data.niceness.values())
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

        # shift back to 0
        max_niceness = None
        if niceness < 0:
            max_niceness = max(rcu_data.niceness.values())
            if max_niceness < niceness:
                # no shifting required
                max_niceness = None
        if niceness > 0:
            max_niceness = niceness
        if max_niceness is not None:
            for k in rcu_data.niceness.keys():
                rcu_data.niceness[k] -= max_niceness
        assert not rcu_data.niceness or 0 in rcu_data.niceness.values()
        assert all(v <= 0 for v in rcu_data.niceness.values())

    def schedule(self, idx, time_slice, rcu_data):
        """See :meth:`TimeSliceFixer.schedule`.

        Checks the niceness for the selected chain and blocks it
        if it's below the :attr:`threshold`.
        """
        if idx == -1:
            return super().schedule(idx, time_slice, rcu_data)

        tid = id(rcu_data.ready_chains[idx].bottom)

        niceness = rcu_data.niceness[tid]

        if time_slice is not None and niceness < self.threshold(time_slice):
            if tid in rcu_data.sat_out_threads:
                # scheduler selected a thread that we wanted to stall again
                # allow it to run then
                # TODO: retry & count retries to self.max_retries
                rcu_data.sat_out_threads.clear()
            else:
                # only nicest thread may run
                nicest_tid = max((id(c.bottom) for c in rcu_data.ready_chains),
                                 key=lambda tid: rcu_data.niceness[tid])
                assert niceness <= rcu_data.niceness[nicest_tid]
                if tid != nicest_tid:
                    rcu_data.sat_out_threads.append(tid)
                    rcu_data.last_timeslice = None
                    return False, None

        rcu_data.last_time_slice = time_slice

        return super().schedule(idx, time_slice, rcu_data)
