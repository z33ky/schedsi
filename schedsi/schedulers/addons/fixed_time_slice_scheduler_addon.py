#!/usr/bin/env python3
"""Defines a scheduler addon that filters time slices.

This allows usage of such schedulers outside the kernel with the
single timer scheduling strategy.
"""

from .. import scheduler


class FixedTimeSliceSchedulerAddon(scheduler.SchedulerAddonBase):
    """Fixed time-slice scheduler-addon."""

    def __init__(self, *args, override_time_slice=None):
        """Create a :class:`FixedTimeSliceSchedulerAddon`."""
        super().__init__(*args)
        self.override_time_slice = override_time_slice

    def schedule(self, _idx, _time_slice, _rcu_data):
        """See :meth:`SchedulerAddonBase.schedule`."""
        return True, self.override_time_slice
