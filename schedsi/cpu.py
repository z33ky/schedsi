#!/usr/bin/env python3
"""Defines a :class:`Core`."""

import enum
from schedsi import threads

CTXSW_COST = 1

_RequestType = enum.Enum('RequestType', ['current_time', 'switch_thread', 'idle', 'execute'])

class Request:
    """A request to the CPU."""

    def __init__(self, rtype, thing):
        """Create a :class:`Request`."""
        if rtype == _RequestType.current_time:
            assert thing is None
        elif rtype == _RequestType.switch_thread:
            assert isinstance(thing, threads.Thread)
        elif rtype == _RequestType.idle:
            assert thing is None
        elif rtype == _RequestType.execute:
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
        return cls(_RequestType.current_time, None)

    @classmethod
    def switch_thread(cls, thread):
        """Create a :class:`Request` to switch context."""
        return cls(_RequestType.switch_thread, thread)

    @classmethod
    def idle(cls):
        """Create a :class:`Request` to idle."""
        return cls(_RequestType.idle, None)

    @classmethod
    def execute(cls, amount):
        """Create a :class:`Request` to spend some time executing."""
        return cls(_RequestType.execute, amount)

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
        self.thread_succ = 0
        self.thread_fail = 0
        self.module_time = 0
        self.module_succ = 0
        self.module_fail = 0

class _TimeStats: # pylint: disable=too-few-public-methods
    """CPU Time statistics."""
    def __init__(self):
        """Create a :class:`_TimeStats`."""
        self.crunch_time = 0
        self.idle_time = 0

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

        Returns a tuple (flag indicating if full time was not used,
                         how much current :attr:`time_slice` allows execution).
        """
        if time > self.time_slice or time == -1:
            time = self.time_slice
            return False, time

        assert time > 0
        return True, time

    def _update_time(self, time):
        """Update the time and check if interrupt happens.

        The arguments should come from :meth:`_calc_runtime`,
        they indicate whether an interrupt should be triggered and
        how much time should pass.

        The functions are separated for logging reasons.
        """
        assert time <= self.time_slice and time > 0

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
        assert self.time_slice == 0
        self.cpu.log.timer_interrupt(self.cpu)
        self.time_slice = self.cpu.timer_quantum
        succeed, time = self._context_switch(self.contexts[0].thread)
        self.contexts[0].thread.run_ctxsw(self.current_time, time)
        if succeed:
            for ctx in self.contexts[1:-1]:
                ctx.thread.finish(self.current_time)
            if self.contexts[-1].started:
                self.contexts[-1].thread.finish(self.current_time)
            del self.contexts[1:]

    def _context_switch(self, thread):
        """Perform a context switch.

        The caller is responsible for modifying the :attr:`contexts` stack
        and call :meth:`Thread.run_ctxsw` on the appropriate :class:`Thread`.
        """
        if thread.module == self.contexts[-1].thread.module:
            self.cpu.log.context_switch(self.cpu, thread, 0, 0)
            self.ctxsw_stats.thread_succ += 1
            return True, 0

        proceed, time = self._calc_runtime(CTXSW_COST)
        assert proceed and time == CTXSW_COST or not proceed and time < CTXSW_COST

        self.cpu.log.context_switch(self.cpu, thread, time, CTXSW_COST)
        self._update_time(time)
        self.ctxsw_stats.module_time += time
        if proceed:
            self.ctxsw_stats.module_succ += 1
        else:
            self.ctxsw_stats.module_fail += 1

        return proceed, time

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
            proceed, time = self._context_switch(self.contexts[-2].thread)
            #who should get this time?
            self.contexts[-1].thread.run_ctxsw(self.current_time, time)
            self._run_background(time)
            if proceed:
                self.contexts[-1].thread.finish(self.current_time)
                self.contexts.pop()

    def _switch_thread(self, thread):
        """Continue execution of another :class:`Thread`.

        The thread must be of either the same :class:`Module` or a child :class:`Module`.
        """
        current_thread = self.contexts[-1].thread
        if not current_thread.module in [thread.module, thread.module.parent]:
            raise RuntimeError('Switching thread to unrelated module')
        proceed, time = self._context_switch(thread)
        #who should get this time?
        thread.run_ctxsw(self.current_time, time)
        self._run_background(time)
        current_thread.run_background(self.current_time, time)
        if proceed:
            self.contexts.append(_Context(thread))

    def execute(self):
        """Execute one step.

        One step is anything that takes time or switching context.
        """
        #For multi-core emulation this should become a coroutine.
        #It should yield whenever current_time is updated.

        if self.time_slice == 0:
            self._timer_interrupt()
            return

        while True:
            next_step = self.contexts[-1].execute(self.current_time)
            if next_step.rtype == _RequestType.current_time:
                #no-op
                continue
            elif next_step.rtype == _RequestType.execute:
                _, time = self._calc_runtime(next_step.thing)
                assert time > 0, time <= next_step
                self.cpu.log.thread_execute(self.cpu, time)
                self._update_time(time)
                self.stats.crunch_time += time
                self._run_background(time)
                self.contexts[-1].thread.run_crunch(self.current_time, time)
            elif next_step.rtype == _RequestType.idle:
                self.cpu.log.thread_yield(self.cpu)
                self._switch_to_parent()
                break
            elif next_step.rtype == _RequestType.switch_thread:
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
