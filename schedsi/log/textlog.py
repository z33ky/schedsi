#!/usr/bin/env python3
"""Defines the :class:`TextLog`."""

import collections
import itertools

Align = collections.namedtuple('Align', 'cpu time module thread')


class TextLog:
    """Text logger.

    Outputs the events in a text file.
    """

    def __init__(self, stream, align=Align(0, 0, 0, 0), *, time_precision):
        """Create a :class:`TextLog`."""
        self.stream = stream
        self.align = align
        # the +1 is for the decimal separator
        self.align = self.align._replace(time=self.align.time + time_precision + 1)
        self.time_prec = time_precision

    def _timespan(self, cost):
        """Stringify a timespan."""
        return '{:.{prec}f} unit{}'.format(cost, '' if cost == 1 else 's', prec=self.time_prec)

    def _ctxsw(self, module_to, time):
        """Stringify a context switch."""
        return 'spends {} to switch to {}'.format(self._timespan(time), module_to.name)

    def _ct(self, cpu):
        """Stringify CPU and time.

        This should be the start of pretty much every message.
        """
        return 'cpu {:>{cpu_align}} @ {:>{time_align}.{prec}f}: '.format(cpu.uid,
                                                                         cpu.status.current_time,
                                                                         cpu_align=self.align.cpu,
                                                                         time_align=self.align.time,
                                                                         prec=self.time_prec)

    def _ctt(self, cpu):
        """Stringify CPU, time and the current thread."""
        thread = cpu.status.chain.top
        module = thread.module
        align = self.align.thread + self.align.module - len(module.name)
        return self._ct(cpu) + 'thread {}-{:<{thread_align}} '.format(module.name, thread.tid,
                                                                      thread_align=align)

    def _ctm(self, cpu, module=None):
        """Stringify CPU, time and the TODO module."""
        # we add alignment to align with _ctt output
        if module is None:
            module = cpu.status.chain.top.module
        else:
            module = cpu.status.chain.thread_at(module).module
        module = module.name
        align = self.align.module + self.align.thread + 1
        return self._ct(cpu) + 'module {:<{module_align}} '.format(module, module_align=align)

    def init_core(self, cpu):
        """Register a :class:`Core`."""
        pass

    def context_switch(self, cpu, split_index, appendix, time):
        """Log an context switch event."""
        if appendix is not None and appendix.bottom.module == cpu.status.chain.top.module:
            self.stream.write(self._ctm(cpu) + 'selects {}.\n'.format(appendix.bottom.tid))

        if time != 0:
            thread_to = appendix and appendix.top or cpu.status.chain.thread_at(split_index)

            self.stream.write(self._ctm(cpu) + '{}.\n'.format(self._ctxsw(thread_to.module, time)))

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        self.stream.write(self._ctt(cpu) + 'runs for {}.\n'.format(self._timespan(runtime)))

    def thread_yield(self, cpu):
        """Log a thread yield event."""
        self.stream.write(self._ctt(cpu) + 'yields.\n')

    def cpu_idle(self, cpu, idle_time):
        """Log an CPU idle event."""
        self.stream.write(self._ct(cpu) + 'idle for {}.\n'.format(self._timespan(idle_time)))

    def timer_interrupt(self, cpu, idx, delay):
        """Log an timer interrupt event."""
        self.stream.write(self._ctm(cpu, idx) + 'timer elapsed')
        if delay:
            self.stream.write(' ({} delay)'.format(self._timespan(delay)))
        self.stream.write('.\n')

    @classmethod
    def to_json(cls, stats, sep_indent='\n'):
        """Convert stats to JSON.

        Works recursively.
        Does formatting differently from the json python module.
        """
        if isinstance(stats, dict):
            next_sep_indent = sep_indent + '\t'
            values = []

            for key, value in sorted(stats.items()):
                # thread keys are (module-name, thread-id) tuples
                # convert to string
                if isinstance(key, tuple):
                    key = '{}-{}'.format(key[0], key[1])

                values.append('"' + key + '": ' + cls.to_json(value, next_sep_indent))

            return '{' + next_sep_indent + (',' + next_sep_indent).join(values) + sep_indent + '}'

        if isinstance(stats, (float, int)):
            return str(stats)

        if isinstance(stats, (list, tuple)):
            return str([list(stat) if isinstance(stat, tuple) else stat for stat in stats])

        if stats is None:
            return '-1'

        assert False, 'Cannot encode {}'.format(type(stats))

    def thread_statistics(self, stats):
        """Log thread statistics."""
        self.stream.write('Thread stats:\n' + self.to_json(stats) + '\n')

    def cpu_statistics(self, stats):
        """Log CPU statistics."""
        self.stream.write('Core stats:\n')
        for sstats, core in zip(sorted(stat.items() for stat in stats), itertools.count()):
            self.stream.write('Core {}\n'.format(core))
            for name, stat in sorted(sstats):
                self.stream.write('\t{}: {}\n'.format(name, stat))
