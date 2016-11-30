#!/usr/bin/env python3
"""Defines the :class:`TextLog`."""

import collections
import itertools

TextLogAlign = collections.namedtuple('TextLogAlign', 'cpu time module thread')

def _timespan(cost):
    """Stringifies a timespan."""
    return "{} unit{}".format(cost, "" if cost == 1 else "s")

def _ctxsw(module_to, time):
    """Stringifies a context switch."""
    return "spends {} to switch to {}".format(_timespan(time), module_to.name)

class TextLog:
    """Text logger.

    Outputs the events in a text file.
    """

    def __init__(self, stream, align=TextLogAlign(0, 0, 0, 0)):
        """Create a :class:`TextLog`."""
        self.stream = stream
        self.align = align

    def _ct(self, cpu):
        """Stringifies CPU and time.

        This should be the start of pretty much every message.
        """
        return "cpu {:>{cpu_align}} @ {:>{time_align}}: ".format(cpu.uid, cpu.status.current_time,
                                                                 cpu_align=self.align.cpu,
                                                                 time_align=self.align.time)

    def _ctt(self, cpu):
        """Stringifies CPU, time and the current thread."""
        module = cpu.status.contexts[-1].thread.module
        thread = cpu.status.contexts[-1].thread
        align = self.align.thread + self.align.module - len(module.name)
        return self._ct(cpu) + "thread {}-{:<{thread_align}} ".format(module.name, thread.tid,
                                                                      thread_align=align)

    def _ctm(self, cpu):
        """Stringifies CPU, time and the current module."""
        #we add alignment to align with _ctt output
        module = cpu.status.contexts[-1].thread.module.name
        align = self.align.module + self.align.thread + 1
        return self._ct(cpu) + "module {:<{module_align}} ".format(module, module_align=align)

    def init_core(self, cpu):
        """Register a :class:`Core`."""
        pass

    def context_switch(self, cpu, thread_to, time):
        """Log an context switch event."""
        if thread_to.module == cpu.status.contexts[-1].thread.module:
            if thread_to.tid == 0:
                return
            self.stream.write(self._ctm(cpu) + "selects {}.\n".format(thread_to.tid))
        else:
            self.stream.write(self._ctm(cpu) + "{}.\n".format(_ctxsw(thread_to.module, time)))

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        self.stream.write(self._ctt(cpu) + "runs for {}.\n".format(_timespan(runtime)))

    def thread_yield(self, cpu):
        """Log a thread yield event."""
        self.stream.write(self._ctt(cpu) + "yields.\n")

    def cpu_idle(self, cpu, idle_time):
        """Log an CPU idle event."""
        self.stream.write(self._ct(cpu) + "idle for {}.\n".format(_timespan(idle_time)))

    def timer_interrupt(self, cpu, delay):
        """Log an timer interrupt event."""
        self.stream.write(self._ct(cpu) + "timer interrupt")
        if delay:
            self.stream.write(" ({} delay)".format(_timespan(delay)))
        self.stream.write(".\n")

    @classmethod
    def to_json(cls, stats, sep_indent="\n"):
        """Convert stats to JSON.

        Works recursively.
        Does formatting differently from the json python module.
        """
        if isinstance(stats, dict):
            next_sep_indent = sep_indent + "\t"
            values = []

            for key, value in sorted(stats.items()):
                #thread keys are (module-name, thread-id) tuples
                #convert to string
                if isinstance(key, tuple):
                    key = '{}-{}'.format(key[0], key[1])

                values.append('"' + key + '": ' + cls.to_json(value, next_sep_indent))

            return "{" + next_sep_indent + ("," + next_sep_indent).join(values) + sep_indent + "}"

        if isinstance(stats, (float, int)):
            return str(stats)

        if isinstance(stats, (list, tuple)):
            return str(list(stats))

        assert False, "Cannot encode {}".format(type(stats))

    def thread_statistics(self, stats):
        """Log thread statistics."""
        self.stream.write("Thread stats:\n" + self.to_json(stats) + "\n")

    def cpu_statistics(self, stats):
        """Log CPU statistics."""
        self.stream.write("Core stats:\n")
        for sstats, core in zip(sorted(stat.items() for stat in stats), itertools.count()):
            self.stream.write("Core {}\n".format(core))
            for name, stat in sorted(sstats):
                self.stream.write("\t{}: {}\n".format(name, stat))
