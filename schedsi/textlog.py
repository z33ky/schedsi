#!/usr/bin/env python3
"""Defines the TextLog."""

import collections

TextLogAlign = collections.namedtuple('TextLogAlign', 'cpu time module thread')

class TextLog:
    """Text logger.

    Outputs the events in a text file.
    """
    def __init__(self, filename, align=TextLogAlign(0, 0, 0, 0)):
        """Create a TextLog."""
        self.file = open(filename, 'x')
        self.align = align

    def _ct(self, cpu, time):
        """Output the CPU and time.

        This should be the start of pretty much every message.
        """
        return "cpu {:>{cpu_align}} @ {:>{time_align}}: ".format(
            cpu.uid, time,
            cpu_align=self.align.cpu,
            time_align=self.align.time
            )

    def _ctt(self, cpu, time, thread):
        """Output the CPU, time and thread."""
        return self._ct(cpu, time) + "thread {:>{thread_align}}-{:<{module_align}} ".format(
            thread.tid, thread.module.name,
            module_align=self.align.module,
            thread_align=self.align.thread
            )

    def _ctm(self, cpu, time, module):
        """Output the CPU, time and module."""
        return self._ct(cpu, time) + "module {:<{module_align}} ".format(
            module.name,
            module_align=self.align.module
            )

    def schedule_none(self, cpu, time, module):
        """Log an "no threads to schedule" event."""
        self.file.write(self._ctm(cpu, time, module) + \
                        "has no threads to schedule.\n")

    def schedule_thread_fail(self, cpu, time, module, cost):
        """Log an "timeout while scheduling" event."""
        self.file.write(self._ctm(cpu, time, module) + \
                        "spent {} units trying to schedule a thread.\n".format(cost))

    def schedule_thread(self, cpu, time, thread, cost):
        """Log an successful scheduling event."""
        self.file.write(self._ctm(cpu, time, thread.module) + \
                        "spent {} units to schedule {}.\n".format(cost, thread.tid))

    def thread_execute(self, cpu, time, thread, runtime):
        """Log an thread execution event."""
        self.file.write(self._ctt(cpu, time, thread) + \
                        "runs for {} units.\n".format(runtime))

    def thread_yield(self, cpu, time, thread):
        """Log an thread yielded event."""
        self.file.write(self._ctt(cpu, time, thread) + \
                        "yields.\n")

    def cpu_idle(self, cpu, time, idle_time):
        """Log an CPU idle event."""
        self.file.write(self._ct(cpu, time) + \
                        "idle for {} units.\n".format(idle_time))

    def timer_interrupt(self, cpu, time):
        """Log an timer interrupt event."""
        self.file.write(self._ct(cpu, time) + \
                        "timer interrupt.\n")
