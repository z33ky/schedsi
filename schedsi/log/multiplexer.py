#!/usr/bin/env python3
"""Defines the :class:`Multiplexer`."""

class Multiplexer:
    """Log multiplexer.

    Forwards log events to multiple log instances.
    """

    def __init__(self, *logs):
        """Create a :class:`Multiplexer`."""
        self._logs = logs

    def init_core(self, cpu):
        """Register a :class:`Core`."""
        for log in self._logs:
            log.init_core(cpu)

    def context_switch(self, cpu, split_index, appendix, time):
        """Log an context switch event."""
        for log in self._logs:
            log.context_switch(cpu, split_index, appendix, time)

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        for log in self._logs:
            log.thread_execute(cpu, runtime)

    def thread_yield(self, cpu):
        """Log an thread yielded event."""
        for log in self._logs:
            log.thread_yield(cpu)

    def cpu_idle(self, cpu, idle_time):
        """Log an CPU idle event."""
        for log in self._logs:
            log.cpu_idle(cpu, idle_time)

    def timer_interrupt(self, cpu, idx, delay):
        """Log an timer interrupt event."""
        for log in self._logs:
            log.timer_interrupt(cpu, idx, delay)

    def thread_statistics(self, stats):
        """Log thread statistics."""
        for log in self._logs:
            log.thread_statistics(stats)

    def cpu_statistics(self, stats):
        """Log CPU statistics."""
        for log in self._logs:
            log.cpu_statistics(stats)
