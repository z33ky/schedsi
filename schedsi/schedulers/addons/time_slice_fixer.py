#!/usr/bin/env python3
"""Defines a scheduler addon that fixes time slices.

With `override_time_slice` set to `None`, this allows the usage of schedulers with time-slices
in scenarios, where timers are not available (e.g. non-kernel modules in the single timer
scheduling approach.
This is also the primary use-case.
"""

from . import addon


class TimeSliceFixer(addon.Addon):
    """Fixed time-slice scheduler-addon."""

    def __init__(self, *args, override_time_slice=None):
        """Create a :class:`TimeSliceFixer`."""
        super().__init__(*args)
        self.override_time_slice = override_time_slice

    def schedule(self, _idx, _time_slice, _rcu_data):
        """See :meth:`Addon.schedule`."""
        return True, self.override_time_slice
