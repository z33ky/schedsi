#!/usr/bin/env python3
"""Defines the TextLog."""

import collections

TextLogAlign = collections.namedtuple('TextLogAlign', 'cpu time module thread')

def _timespan(cost):
    """Stringifies a timespan."""
    return "{} unit{}".format(cost, "" if cost == 1 else "s")

def _ctxsw(module_to, time, required):
    """Stringifies a context switch."""
    if time < required:
        time = "{}/{} trying".format(time, _timespan(required))
    else:
        time = _timespan(time)
    return "spends {} to switch to {}".format(time, module_to.name)

class TextLog:
    """Text logger.

    Outputs the events in a text file.
    """
    def __init__(self, stream, align=TextLogAlign(0, 0, 0, 0)):
        """Create a TextLog."""
        self.stream = stream
        self.align = align

    def _ct(self, cpu):
        """Stringifies a CPU and time.

        This should be the start of pretty much every message.
        """
        return "cpu {:>{cpu_align}} @ {:>{time_align}}: ".format(cpu.uid, cpu.status.current_time,
                                                                 cpu_align=self.align.cpu,
                                                                 time_align=self.align.time)

    def _ctt(self, cpu):
        """Stringifies a CPU, time and a thread."""
        module = cpu.status.context.module
        thread = cpu.status.context.thread
        align = self.align.thread + self.align.module - len(module.name)
        return self._ct(cpu) + "thread {}-{:<{thread_align}} ".format(module.name, thread.tid,
                                                                      thread_align=align)

    def _ctm(self, cpu):
        """Stringifies a CPU, time and a module."""
        #we add alignment to align with _ctt output
        module = cpu.status.context.module
        align = self.align.module + self.align.thread + 1
        return self._ct(cpu) + "module {:<{module_align}} ".format(module.name, module_align=align)

    def module_yield(self, cpu, module_to, time, required):
        """Log an "module yields (usually to parent)" event."""
        self.stream.write(self._ctm(cpu) + "{}.\n".format(_ctxsw(module_to, time, required)))

    def schedule_thread(self, cpu):
        """Log an successful scheduling event."""
        thread = cpu.status.context.thread
        self.stream.write(self._ctm(cpu) + "selects {}.\n".format(thread.tid))

    def context_switch(self, cpu, module_to, time, required):
        """Log an context switch event."""
        self.stream.write(self._ctm(cpu) + "{}.\n".format(_ctxsw(module_to, time, required)))

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        self.stream.write(self._ctt(cpu) + "runs for {}.\n".format(_timespan(runtime)))

    def thread_yield(self, cpu):
        """Log a thread yield event."""
        self.stream.write(self._ctt(cpu) + "yields.\n")

    def kernel_yield(self, cpu):
        """Log a kernel yield event."""
        self.stream.write(self._ctm(cpu) + "yields.\n")

    def cpu_idle(self, cpu, idle_time):
        """Log an CPU idle event."""
        self.stream.write(self._ct(cpu) + "idle for {}.\n".format(_timespan(idle_time)))

    def timer_interrupt(self, cpu):
        """Log an timer interrupt event."""
        self.stream.write(self._ct(cpu) + "timer interrupt.\n")
