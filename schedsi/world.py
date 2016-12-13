#!/usr/bin/env python3
"""Defines the :class:`World`."""

import io
from schedsi import binarylog, cpu


class World:
    """The world keeps data to enable execution."""

    def __init__(self, cores, kernel, log=binarylog.BinaryLog(io.BytesIO()), *,
                 local_timer_scheduling):
        """Create a :class:`World`."""
        if cores > 1:
            raise RuntimeError('Does not support more than 1 core yet.')
        self.cores = [cpu.Core(idx, kernel._scheduler_thread, log,
                               local_timer_scheduling=local_timer_scheduling)
                      for idx in range(0, cores)]
        for core in self.cores:
            kernel.register_vcpu(core)
        self.log = log

    def step(self):
        """Execute one timer quantum for each :class:`~schedsi.cpu.Core` in the \
        :class:`World`."""
        assert len(self.cores) == 1
        core = self.cores[0]
        core.execute()
        # FIXME: threads becoming ready while idling
        return core.status.current_time

    def log_statistics(self):
        """Log statistics."""
        kernel = self.cores[0].kernel
        # there should be only one kernel?
        assert all(c.kernel == kernel for c in self.cores)
        self.log.thread_statistics(kernel.get_thread_statistics())
        self.log.cpu_statistics(core.get_statistics() for core in self.cores)
