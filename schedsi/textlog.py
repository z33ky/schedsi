#!/usr/bin/env python3
"""Defines the TextLog."""

import collections

TextLogAlign = collections.namedtuple('TextLogAlign', 'cpu time module thread')

def _timespan(cost):
    """Stringifies a timespan."""
    return "{} unit{}".format(cost, "" if cost == 1 else "s")

class TextLog:
    """Text logger.

    Outputs the events in a text file.
    """
    def __init__(self, stream, align=TextLogAlign(0, 0, 0, 0)):
        """Create a TextLog."""
        self.stream = stream
        self.align = align

    def _ct(self, cpu, time):
        """Stringifies a CPU and time.

        This should be the start of pretty much every message.
        """
        return "cpu {:>{cpu_align}} @ {:>{time_align}}: ".format(
            cpu.uid, time,
            cpu_align=self.align.cpu,
            time_align=self.align.time
            )

    def _ctt(self, cpu, time, thread):
        """Stringifies a CPU, time and a thread."""
        return self._ct(cpu, time) + "thread {}-{:<{thread_align}} ".format(
            thread.module.name, thread.tid,
            thread_align=self.align.thread + self.align.module - len(thread.module.name)
            )

    def _ctm(self, cpu, time, module):
        """Stringifies a CPU, time and a module."""
        return self._ct(cpu, time) + "module {:<{module_align}} ".format(
            module.name,
            #we add alignment to align with _ctt output
            module_align=self.align.module + self.align.thread + 1
            )

    def schedule_none(self, cpu, time, module):
        """Log an "no threads to schedule" event."""
        self.stream.write(self._ctm(cpu, time, module) + \
                        "has no threads to schedule.\n")

    def schedule_thread(self, cpu, time, thread):
        """Log an successful scheduling event."""
        self.stream.write(self._ctm(cpu, time, thread.module) + \
                        "selects {}.\n".format(thread.tid))

    def context_switch(self, cpu, time, module_from, module_to, cost):
        """Log an context switch event."""
        self.stream.write(self._ctm(cpu, time, module_from) + \
                        "spends {} to switch to {}.\n".format(_timespan(cost), module_to.name))

    def context_switch_fail(self, cpu, time, module_from, module_to, cost):
        """Log an "timeout while scheduling" event."""
        self.stream.write(self._ctm(cpu, time, module_from) + \
                        "spends {} trying to switch to {}.\n".format(_timespan(cost),
                                                                     module_to.name))

    def thread_execute(self, cpu, time, thread, runtime):
        """Log an thread execution event."""
        self.stream.write(self._ctt(cpu, time, thread) + \
                        "runs for {}.\n".format(_timespan(runtime)))

    def thread_yield(self, cpu, time, thread):
        """Log an thread yielded event."""
        self.stream.write(self._ctt(cpu, time, thread) + \
                        "yields.\n")

    def cpu_idle(self, cpu, time, idle_time):
        """Log an CPU idle event."""
        self.stream.write(self._ct(cpu, time) + \
                        "idle for {}.\n".format(_timespan(idle_time)))

    def timer_interrupt(self, cpu, time):
        """Log an timer interrupt event."""
        self.stream.write(self._ct(cpu, time) + \
                        "timer interrupt.\n")
