#!/usr/bin/env python3
"""Defines the World."""

import io
from schedsi import binarylog, cpu

class World: # pylint: disable=too-few-public-methods
    """The World."""

    def __init__(self, cores, timer_quantum, kernel, log=binarylog.BinaryLog(io.BytesIO())):
        """Creates a world."""
        if cores > 1:
            #supporting this will be difficult
            #one approach might be using coroutines
            raise RuntimeError("Does not support more than 1 core yet.")
        self.cores = [cpu.Core(idx, timer_quantum, kernel, log) for idx in range(0, cores)]
        self.kernel = kernel
        self.log = log

    def step(self):
        """Executes one timer quantum for each CPU in the world."""
        assert len(self.cores) == 1
        core = self.cores[0]
        self.kernel.schedule(core)
        #FIXME: threads becoming ready while idling
        core.finish_step(self.kernel)
        return core.status.current_time
