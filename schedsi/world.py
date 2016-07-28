#!/usr/bin/env python3
"""Defines the World."""

import collections

#TODO: move this?
Core = collections.namedtuple('Core', 'uid timer_quantum')

class World: # pylint: disable=too-few-public-methods
    """The World."""

    def __init__(self, cpu, kernel):
        """Creates a world."""
        self.current_time = 0
        self.cpu = cpu
        self.kernel = kernel

    def step(self, log):
        """Executes one timer quantum for each CPU in the world."""
        left = self.kernel.schedule(self.cpu, self.current_time, self.cpu.timer_quantum, log)
        self.current_time += self.cpu.timer_quantum - left
        #FIXME: threads becoming ready while idling
        if left > 0:
            log.cpu_idle(self.cpu, self.current_time, left)
        self.current_time += left
        log.timer_interrupt(self.cpu, self.current_time)
        #FIXME: context switch from * back to kernel
        return self.current_time
