#!/usr/bin/env python3
"""Defines a scheduler addon that maximizes run-times to time slices.

Basically, the :class:`TimeSliceMaxer` repeats the scheduler's decision
until it ran for at least `time_slice - threshold` units (or the thread is finished).
"""

from . import time_slice_fixer


class TimeSliceMaxerData():  # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`TimeSliceMaxer`."""

    def __init__(self):
        """Create a :class:`TimeSliceMaxerData`."""
        self.repeat_time_slices = {}
        self.blocked = False

class TimeSliceMaxer(time_slice_fixer.TimeSliceFixer):
    """Maximizing time-slice scheduler-addon."""

    def __init__(self, *args, override_time_slice=None, threshold=0):
        """Create a :class:`TimeSliceMaxer`."""
        super().__init__(*args, override_time_slice=override_time_slice)
        self.threshold = threshold

    def transmute_rcu_data(self, original, *addon_data):  # pylint: disable=no-self-use
        """See :meth:`Addon.transmute_rcu_data`."""
        super().transmute_rcu_data(original, TimeSliceMaxerData, *addon_data)

    def repeat(self, rcu_data, prev_run_time, done):
        """See :meth:`Addon.repeat`."""
        idx = rcu_data.last_idx
        if idx is None or rcu_data.blocked:
            assert not rcu_data.repeat_time_slices
            return None, None
        if done:
            del rcu_data.repeat_time_slices[idx]
            return None, None

        time_slice = rcu_data.repeat_time_slices[idx]

        if time_slice is None:
            return True, time_slice

        time_slice -= prev_run_time
        if time_slice > self.threshold:
            rcu_data.repeat_time_slices[idx] = time_slice
            return True, time_slice

        del rcu_data.repeat_time_slices[idx]
        return None, None

    def schedule(self, idx, time_slice, rcu_data):
        """See :meth:`Addon.schedule`."""
        if idx in rcu_data.repeat_time_slices:
            assert rcu_data.repeat_time_slices[idx] == time_slice
            proceed, *rest = super().schedule(None, time_slice, rcu_data)
        else:
            if idx is None:
                rcu_data.repeat_time_slices.clear()
            assert not rcu_data.repeat_time_slices
            proceed, *rest = super().schedule(idx, time_slice, rcu_data)

        if proceed and idx is not None:
            rcu_data.repeat_time_slices[idx] = time_slice
            rcu_data.blocked = False
        else:
            assert not rcu_data.repeat_time_slices
            rcu_data.blocked = True
        return (proceed, *rest)
