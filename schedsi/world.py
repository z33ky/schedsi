#!/usr/bin/env python3
"""Defines the :class:`World`."""

import io
from schedsi import binarylog, cpu

class World:
    """The world keeps data to enable execution."""

    def __init__(self, cores, timer_quantum, kernel, log=binarylog.BinaryLog(io.BytesIO())):
        """Creates a :class:`World`."""
        if cores > 1:
            raise RuntimeError("Does not support more than 1 core yet.")
        self.cores = [cpu.Core(idx, timer_quantum, kernel._scheduler_thread, log)
                      for idx in range(0, cores)]
        for core in self.cores:
            kernel.register_vcpu(core)
        self.log = log

    def step(self):
        """Executes one timer quantum for each :class:`Core <schedsi.cpu.Core>` in the
        :class:`World`."""
        assert len(self.cores) == 1
        core = self.cores[0]
        core.execute()
        #FIXME: threads becoming ready while idling
        return core.status.current_time

    def log_statistics(self):
        """Log statistics."""
        self.log.cpu_statistics(core.get_statistics() for core in self.cores)
