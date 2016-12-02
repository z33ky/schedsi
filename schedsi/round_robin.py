#!/usr/bin/env python3
"""Defines a preemptible Round Robin scheduler."""

from schedsi import multilevel_feedback_queue

class RoundRobin(multilevel_feedback_queue.MLFQ):
    """RoundRobin scheduler.

    Since MLFQ does round robin on the active queue,
    this scheduler is simply implemented as MLFQ with 1 queue.
    """

    def __init__(self, module, **kwargs):
        """Create a :class:`RoundRobin` scheduler."""
        super().__init__(module, levels=1, priority_boost_time=None, **kwargs)
