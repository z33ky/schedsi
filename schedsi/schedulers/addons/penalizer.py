#!/usr/bin/env python3
"""Defines a scheduler addon, that penalizes threads running more than their allotted time-slices.

Unlike the :class:`PenaltyTracker`, this addon only tracks time debt.
"""

from . import time_slice_fixer
from schedsi.cpu.time import Time


class PenalizerData():  # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`Penalizer`."""

    def __init__(self):
        """Create a :class:`PenalizerData`."""
        self.sat_out_threads = []
        self.last_time_slice = None
        self.niceness = {}


class Penalizer(time_slice_fixer.TimeSliceFixer):
    """Penalizing scheduler-addon.

    `niceness` is always <= 0 and represents how much longer the chain ran
    than the time-slice specified.

    A function :attr:`block` determines whether the `niceness` of a :class:`Thread`
    warrants blocking it from being scheduled.
    """

    def __init__(self, *args, override_time_slice=None, tolerance=0):
        """Create a :class:`Penalizer`.

        `block` is a function that takes the niceness of the scheduled thread
        as selected by the :class:`Scheduler`, a `dict` of the `niceness`es of all
        ready threads and a `list` of :class:`Thread`-ids currently blocked and returns
        a `bool` indicating whether to block the selected :class:`Thread`.
        The `dict` of `niceness`es has :class:`Thread`-id's as keys.
        """
        super().__init__(*args, override_time_slice=override_time_slice)
        assert tolerance <= 0
        self.tolerance = tolerance

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
                    delta = rcu_data.last_time_slice - prev_run_time
                    if delta < 0:
                        rcu_data.niceness[last_id] += delta
                    niceness = rcu_data.niceness[last_id]
            rcu_data.last_time_slice = None
        else:
            assert rcu_data.last_time_slice is None

        if rcu_data.sat_out_threads:
            assert last_chain
            if last_id != rcu_data.sat_out_threads[-1]:
                assert prev_run_time > 0
                for tid in rcu_data.sat_out_threads:
                    if rcu_data.niceness[tid] < 0:
                        # TODO: do we want to keep niceness <= 0 with min?
                        rcu_data.niceness[tid] += min(-rcu_data.niceness[tid], prev_run_time)
                        niceness = max(niceness, rcu_data.niceness[tid])
                rcu_data.sat_out_threads.clear()

        # shift back to 0
        if niceness < 0:
            max_niceness = max(rcu_data.niceness.values())
            if max_niceness >= niceness:
                for k in rcu_data.niceness.keys():
                    rcu_data.niceness[k] -= max_niceness
        assert not rcu_data.niceness or 0 in rcu_data.niceness.values()
        assert all(v <= 0 for v in rcu_data.niceness.values())

    def schedule(self, idx, time_slice, rcu_data):
        """See :meth:`TimeSliceFixer.schedule`.

        Checks the niceness for the selected chain and blocks it
        if it's below the :attr:`tolerance`.
        """
        if idx == -1:
            return super().schedule(idx, time_slice, rcu_data)

        tid = id(rcu_data.ready_chains[idx].bottom)

        if tid in rcu_data.sat_out_threads:
            # scheduler selected a thread that we wanted to stall again
            # allow it to run then
            # TODO: retry & count retries to self.max_retries
            rcu_data.sat_out_threads.clear()
        elif len(rcu_data.ready_chains) > 1:
            if rcu_data.niceness[tid] < self.tolerance:
                rcu_data.sat_out_threads.append(tid)
                rcu_data.last_time_slice = None
                super().schedule(-1, None, rcu_data)
                return False, None

        rcu_data.last_time_slice = time_slice

        return super().schedule(idx, time_slice, rcu_data)
