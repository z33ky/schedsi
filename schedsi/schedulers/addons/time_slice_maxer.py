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

class TimeSliceMaxer(time_slice_fixer.TimeSliceFixer):
    """Maximizing time-slice scheduler-addon."""

    def __init__(self, *args, override_time_slice=None, threshold=0):
        """Create a :class:`TimeSliceMaxer`."""
        super().__init__(*args, override_time_slice=override_time_slice)
        self.threshold = threshold

    def transmute_rcu_data(self, original, *addon_data):  # pylint: disable=no-self-use
        """See :meth:`Addon.transmute_rcu_data`."""
        super().transmute_rcu_data(original, TimeSliceMaxerData, *addon_data)

    def repeat(self, rcu_data, prev_run_time):
        """See :meth:`Addon.repeat`."""
        idx = rcu_data.last_idx
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
        rcu_data.repeat_time_slices[idx] = time_slice
        return super().schedule(idx, time_slice, rcu_data)
