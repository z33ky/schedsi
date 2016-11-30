#!/usr/bin/env python3
"""Defines a :class:`Core`."""

import enum
from schedsi import threads

CTXSW_COST = 1

RequestType = enum.Enum('RequestType', ['current_time', 'switch_thread', 'idle', 'execute'])

class Request:
    """A request to the CPU."""

    def __init__(self, rtype, thing):
        """Create a :class:`Request`."""
        if rtype == RequestType.current_time:
            assert thing is None
        elif rtype == RequestType.switch_thread:
            assert isinstance(thing, threads.Thread)
        elif rtype == RequestType.idle:
            assert thing is None
        elif rtype == RequestType.execute:
            assert thing > 0 or thing == -1
        else:
            assert False
        self.rtype = rtype
        self.thing = thing

    @classmethod
    def current_time(cls):
        """Create a :class:`Request` to get the current time.

        The CPU will not spend any virtual time doing this.
        """
        return cls(RequestType.current_time, None)

    @classmethod
    def switch_thread(cls, thread):
        """Create a :class:`Request` to switch context."""
        return cls(RequestType.switch_thread, thread)

    @classmethod
    def idle(cls):
        """Create a :class:`Request` to idle."""
        return cls(RequestType.idle, None)

    @classmethod
    def execute(cls, amount):
        """Create a :class:`Request` to spend some time executing."""
        return cls(RequestType.execute, amount)

class _Context: # pylint: disable=too-few-public-methods
    """An operation context for a CPU Core.

    The context has
        * the current :class:`Thread`
        * the execution coroutine of the :class:`Thread`
    """

    def __init__(self, thread):
        """Create a :class:`_Context`"""
        self.thread = thread
        self.execution = thread.execute()
        self.started = False

    def execute(self, current_time):
        """Run the execution coroutine."""
        if self.started:
            return self.execution.send(current_time)
        else:
            self.started = True
            return next(self.execution)

class _ContextSwitchStats: # pylint: disable=too-few-public-methods
    """Context switching statistics."""

    def __init__(self):
        """Create a :class:`_ContextSwitchStats`."""
        self.thread_time = 0
        self.module_time = 0

class _TimeStats: # pylint: disable=too-few-public-methods
    """CPU Time statistics."""
    def __init__(self):
        """Create a :class:`_TimeStats`."""
        self.crunch_time = 0
        self.idle_time = 0
        self.timer_delay = 0

class _Status:
    """Status of a CPU Core.

    The Status consists of:
        * a reference to the :class:`Core` that owns it
        * a stack of operation :class:`_Contexts <_Context>`
        * the current time slice (or what's left of it)
        * the current time
        * :class:`_TimeStats`
        * :class:`_ContextSwitchStats`
    """

    def __init__(self, cpu, context):
        """Create a :class:`_Status`."""
        self.cpu = cpu
        self.contexts = [context]
        self.time_slice = cpu.timer_quantum
        self.current_time = 0
        self.stats = _TimeStats()
        self.ctxsw_stats = _ContextSwitchStats()

    def _calc_runtime(self, time):
        """Calculate the execution time available.

        If the :attr:`time_slice` is shorter, then the operation
        would be interrupted. This function evaluates this.

        -1 is considered "as long as possible".

        Also see :meth:`_update_time`.

        Returns how long the current :attr:`time_slice` allows execution for.
        """
        if time > self.time_slice or time == -1:
            time = max(0, self.time_slice)

        assert time >= 0
        return time

    def _update_time(self, time):
        """Update the time and check if interrupt happens.

        `time` must not be negative.
        """
        assert time > 0

        self.current_time += time
        self.time_slice -= time

    def _run_background(self, time):
        """Call :meth:`Thread.run_background` on each :class:`Thread` in the
        :class:`_Context` stack except the last (most recent).
        """
        for ctx in self.contexts[0:-1]:
            ctx.thread.run_background(self.current_time, time)

    def _timer_interrupt(self):
        """Call when the :attr:`time_slice` runs out.

        Sets up a new :attr:`time_slice` and jumps back to the kernel.
        """
        assert self.time_slice <= 0

        self.cpu.log.timer_interrupt(self.cpu, -self.time_slice)
        time = self._context_switch(self.contexts[0].thread)
        self.stats.timer_delay += -self.time_slice
        #subtract overrun from next time slice
        #note that self.time_slice is negative, so + is correct
        self.time_slice = self.cpu.timer_quantum + self.time_slice
        assert self.time_slice > 0, "CTXSW_COST is too big or timer_quantum too small"

        self.contexts[0].thread.run_ctxsw(self.current_time, time)
        for ctx in self.contexts[1:-1]:
            ctx.thread.finish(self.current_time)
        if self.contexts[-1].started and len(self.contexts) > 1:
            self.contexts[-1].thread.finish(self.current_time)
        del self.contexts[1:]

    def _context_switch(self, thread):
        """Perform a context switch.

        The caller is responsible for modifying the :attr:`contexts` stack
        and call :meth:`Thread.run_ctxsw` on the appropriate :class:`Thread`.

        Returns the context switching time.
        """
        if thread.module == self.contexts[-1].thread.module:
            self.cpu.log.context_switch(self.cpu, thread, 0)
            #self.ctxsw_stats.thread_time += 0
            return 0

        self.cpu.log.context_switch(self.cpu, thread, CTXSW_COST)
        self.ctxsw_stats.module_time += CTXSW_COST

        time = self._calc_runtime(CTXSW_COST)
        self._update_time(CTXSW_COST)
        assert time == CTXSW_COST or self.time_slice <= 0

        return CTXSW_COST

    def _switch_to_parent(self):
        """Return execution to the parent :class:`Thread`."""
        if len(self.contexts) == 1:
            #kernel yields
            self.cpu.log.cpu_idle(self.cpu, self.time_slice)
            thread = self.contexts.pop().thread
            thread.finish(self.current_time)
            self.contexts.append(_Context(thread))
            self.stats.idle_time += self.time_slice
            self._update_time(self.time_slice)
        else:
            time = self._context_switch(self.contexts[-2].thread)
            #who should get this time?
            self.contexts[-1].thread.run_ctxsw(self.current_time, time)
            self._run_background(time)
            self.contexts[-1].thread.finish(self.current_time)
            self.contexts.pop()

    def _switch_thread(self, thread):
        """Continue execution of another :class:`Thread`.

        The thread must be of either the same :class:`Module` or a child :class:`Module`.
        """
        current_thread = self.contexts[-1].thread
        if not current_thread.module in [thread.module, thread.module.parent]:
            raise RuntimeError('Switching thread to unrelated module')
        time = self._context_switch(thread)
        #who should get this time?
        current_thread.run_ctxsw(self.current_time, time)
        self._run_background(time)
        current_thread.run_background(self.current_time, time)
        self.contexts.append(_Context(thread))

    def execute(self):
        """Execute one step.

        One step is anything that takes time or switching context.
        """
        #For multi-core emulation this should become a coroutine.
        #It should yield whenever current_time is updated.

        if self.time_slice <= 0:
            self._timer_interrupt()
            return

        while True:
            next_step = self.contexts[-1].execute(self.current_time)
            if next_step.rtype == RequestType.current_time:
                #no-op
                continue
            elif next_step.rtype == RequestType.execute:
                time = self._calc_runtime(next_step.thing)
                assert time > 0, time <= next_step
                self.cpu.log.thread_execute(self.cpu, time)
                self.stats.crunch_time += time
                self._update_time(time)
                self._run_background(time)
                self.contexts[-1].thread.run_crunch(self.current_time, time)
            elif next_step.rtype == RequestType.idle:
                self.cpu.log.thread_yield(self.cpu)
                self._switch_to_parent()
                break
            elif next_step.rtype == RequestType.switch_thread:
                self._switch_thread(next_step.thing)
            else:
                assert False
            break

class Core:
    """A CPU Core.

    The Core has:
        * a unique ID
        * the timer quantum
        * a log to report its actions to
        * the :class:`_Status`

    The values are not expected to change much during operation.
    """

    def __init__(self, uid, timer_quantum, init_thread, log):
        """Create a :class:`Core`."""
        self.uid = uid
        self.timer_quantum = timer_quantum

        self.log = log

        self.status = _Status(self, _Context(init_thread))

        log.init_core(self)

    def execute(self):
        """Execute one step.

        See :meth:`_Context.execute`.
        """
        self.status.execute()

    def get_statistics(self):
        """Obtain statistics."""
        stats = self.status.stats.__dict__.copy()
        stats.update(self.status.ctxsw_stats.__dict__)
        return stats
