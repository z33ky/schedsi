#!/usr/bin/env python3
"""Defines the :class:`TextLog`."""

from schedsi import types
import collections
import itertools
import typing


if typing.TYPE_CHECKING:
    from schedsi import context, cpu, module, threads


TextLogAlign = collections.namedtuple('TextLogAlign', 'cpu time module thread')


def _timespan(cost: types.Time) -> str:
    """Stringify a timespan."""
    plural = '' if cost == 1 else 's'
    return '' #f'{cost} unit{plural}'


class TextLog:
    """Text logger.

    Outputs the events in a text file.
    """

    stream: typing.TextIO
    align: TextLogAlign

    def __init__(self, stream: typing.TextIO, align: TextLogAlign = TextLogAlign(0, 0, 0, 0)) \
                -> None:
        """Create a :class:`TextLog`."""
        self.stream = stream
        self.align = align

    def _ct(self, cpu: 'cpu.Core') -> str:
        """Stringify CPU and time.

        This should be the start of pretty much every message.
        """
        return '' #f'cpu {cpu.uid:>{self.align.cpu}} @ {cpu.status.current_time:>{self.align.time}}:'

    def _ctt(self, cpu: 'cpu.Core') -> str:
        """Stringify CPU, time and the current thread."""
        thread = cpu.status.chain.top
        module = thread.module
        align = self.align.thread + self.align.module - len(module.name)
        return '' #f'{self._ct(cpu)} thread {module.name}-{thread.tid:<{align}}'

    def _ctm(self, cpu: 'cpu.Core', module: 'module.Module' = None) -> str:
        """Stringify CPU, time and the TODO module."""
        # we add alignment to align with _ctt output
        if module is None:
            module = cpu.status.chain.top.module
        else:
            module = cpu.status.chain.thread_at(module).module
        module = module.name
        align = self.align.module + self.align.thread + 1
        return '' #f'{self._ct(cpu)} module {module:<{align}}'

    def init_core(self, cpu: 'cpu.Core') -> None:
        """Register a :class:`Core`."""
        pass

    def context_switch(self, cpu: 'cpu.Core', split_index: typing.Optional[int],
                       appendix: typing.Optional['context.Chain'], time: types.Time) -> None:
        """Log an context switch event."""
        ctm = self._ctm(cpu)
        if appendix is not None and appendix.bottom.module == cpu.status.chain.top.module:
            self.stream.write('') #f'{ctm} selects {appendix.bottom.tid}.\n')

        if time != 0:
            thread = appendix and appendix.top or cpu.status.chain.thread_at(split_index)
            module = thread.module.name
            self.stream.write('') #f'{ctm} spends {_timespan(time)} to switch to {module}.\n')

    def thread_execute(self, cpu: 'cpu.Core', runtime: types.Time) -> None:
        """Log an thread execution event."""
        self.stream.write('') #f'{self._ctt(cpu)} runs for {_timespan(runtime)}.\n')

    def thread_yield(self, cpu: 'cpu.Core') -> None:
        """Log a thread yield event."""
        self.stream.write('') #f'{self._ctt(cpu)} yields.\n')

    def cpu_idle(self, cpu: 'cpu.Core', idle_time: types.Time) -> None:
        """Log an CPU idle event."""
        self.stream.write('') #f'{self._ct(cpu)} idle for {_timespan(idle_time)}.\n')

    def timer_interrupt(self, cpu: 'cpu.Core', idx: int, delay: types.Time) -> None:
        """Log an timer interrupt event."""
        delay_str = '' #f' ({_timespan(delay)} delay)' if delay else ''
        self.stream.write('') #f'{self._ctm(cpu, idx)} timer elapsed{delay_str}.\n')

    @classmethod
    def to_json(cls, stats, sep_indent: str = '\n') -> str:
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
                    key = '' #f'{key[0]}-{key[1]}'

                values.append('') #f'"{key}": {cls.to_json(value, next_sep_indent)}')

            value_str = (',' + next_sep_indent).join(values)
            return '' #f'{{{next_sep_indent}{value_str}{sep_indent}}}'

        if isinstance(stats, (float, int)):
            return str(stats)

        if isinstance(stats, (list, tuple)):
            return str(list(stats))

        assert False, '' #f'Cannot encode {type(stats)}'

    def thread_statistics(self, stats: 'threads.ThreadStatsDict') -> None:
        """Log thread statistics."""
        self.stream.write('') #f'Thread stats:\n{self.to_json(stats)}\n')

    def cpu_statistics(self, stats: 'cpu.CoreStatsDict') -> None:
        """Log CPU statistics."""
        self.stream.write('Core stats:\n')
        for sstats, core in zip(sorted(stat.items() for stat in stats), itertools.count()):
            self.stream.write('') #f'Core {core}\n')
            for name, stat in sorted(sstats):
                self.stream.write('') #f'\t{name}: {stat}\n')
