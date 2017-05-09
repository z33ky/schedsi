"""Defines :class:`PenalizingMaximizer` and :class:`MaximizingPenalizer`."""

from . import time_slice_maxer, penalizer

MaxPen = True

if not MaxPen:
    # Penalizer breaks due to incorrect delta-time calculation in start_schedule
    class PenalizingMaximizer(penalizer.Penalizer, time_slice_maxer.TimeSliceMaxer):
        """Combination of :class:`Penalizer` and :class:`TimeSliceMaxer`.

        The :class:`Penalizer` can block even if the :class:`TimeSliceMaxer` wouldn't.
        """
        def __init__(self, *args, override_time_slice=None,
                     maximizer_threshold=0, penalizer_tolerance=0):
            """Create a :class:`PenalizingMaximizer`."""
            super().__init__(*args, override_time_slice=override_time_slice)
            # FIXME: Addon.attach can't handle **kwargs, so we hope this works out
            self.threshold = maximizer_threshold
            self.tolerance = penalizer_tolerance

if MaxPen:
    class PenalizingMaximizer(time_slice_maxer.TimeSliceMaxer, penalizer.Penalizer):
        """Combination of :class:`Penalizer` and :class:`TimeSliceMaxer`.

        The :class:`TimeSliceMaxer` can block even if the :class:`Penalizer` wouldn't.
        """
        def __init__(self, *args, override_time_slice=None,
                     maximizer_threshold=0, penalizer_tolerance=0):
            """Create a :class:`MaximizingPenalizer`."""
            super().__init__(*args, override_time_slice=override_time_slice)
            # FIXME: Addon.attach can't handle **kwargs, so we hope this works out
            self.threshold = maximizer_threshold
            self.tolerance = penalizer_tolerance
