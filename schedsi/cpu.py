#!/usr/bin/env python3
"""Defines a Core."""

CTXSW_COST = 1

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

class _Context:
    """An operation context for a CPU Core.

    The context has
        * a reference to the :class:`_Status` that owns it
        * the current :class:`Thread`
        * the current :class:`Module`
        * the :class:`Module` that was active when the timer interrupt came
        * the :class:`Module` that will be switched to
        * context switch statistics
    """

    def __init__(self, cpu, kernel):
        """Create a :class:`_Context`"""
        self.cpu = cpu
        self.thread = None
        self.module = kernel
        self.module_int = None
        self.yield_to = None
        self.ctxsw_stats = _ContextSwitchStats()

    def switch_module(self, module):
        """See :func:`_Status.switch_module`."""
        log = self.cpu.log
        status = self.cpu.status
        if module == self.module:
            print("Context switch to already active module; Ignoring")
            return 0
        else:
            if self.module_int:
                assert self.cpu.status.pending_interrupt is False
                self.module = self.module_int
                self.module_int = None
                if module == self.module:
                    return 0

            interrupted, time = status.calc_time(CTXSW_COST)

            if self.yield_to:
                if self.yield_to != module:
                    raise RuntimeError('yield_to is not yielded to')
                self.yield_to = None
            log.context_switch(self.cpu, module, time, CTXSW_COST)

            status.update_time(interrupted, time)
            self.ctxsw_stats.module_time += time
            if not interrupted:
                self.ctxsw_stats.module_succ += 1
                self.module = module
            else:
                self.ctxsw_stats.module_fail += 1
                self.interrupt()
                self.module_int = None
            return time

    def interrupt(self):
        """Prepare for context switch after timer interrupt."""
        self.module_int = self.module
        self.module = None
        self.thread = None

    def yield_module(self, module):
        """See :func:`_Status.yield_module`."""
        if self.module_int:
            raise RuntimeError('Module trying to yield during interrupt')
        if self.yield_to:
            raise RuntimeError('Two yields without context switch')
        if module != self.module:
            raise RuntimeError('Module != current context')
        if module.parent:
            self.yield_to = module.parent

    def switch_thread(self, thread):
        """See :func:`_Status.switch_thread`."""
        if thread == self.thread:
            print("Thread switch to already active thread; Ignoring")
            return 0
        #TODO: thread switch cost
        if thread.module != self.module:
            raise RuntimeError('Thread not in current context')
        self.ctxsw_stats.thread_succ += 1
        self.thread = thread
        self.cpu.log.schedule_thread(self.cpu)

        return 0

class _TimeStats: # pylint: disable=too-few-public-methods
    """CPU Time statistics."""
    def __init__(self):
        """Create a :class:`_TimeStats`."""
        self.crunch_time = 0
        self.idle_time = 0

class _Status:
    """Status or a CPU Core.

    The Status consists of:
        * a reference to the :class:`Core` that owns it
        * an operation :class:`_Context`
        * the current time slice (or what's left of it)
        * the current time
        * a flag indicating a pending interrupt
        * time statistics

    An interrupt will be pending when the time slice is used up while
    there are still threads wanting CPU time.
    While an interrupt is pending, no other computation can happen.
    Operation can be resumed after calling :func:`finish_step`.
    """
    def __init__(self, cpu, context):
        """Create a :class:`_Status`."""
        self.cpu = cpu
        self.context = context
        self.time_slice = cpu.timer_quantum
        self.current_time = 0
        self.pending_interrupt = False
        self.stats = _TimeStats()

    def calc_time(self, time):
        """Calculate the execution time available.

        If the time slice is shorter, then the operation would be interrupted.
        This function evaluates this.

        -1 is considered "as long as possible".

        Returns a tuple (flag indicating if full time can be used,
                         how much current time slice allows execution).
        """
        assert not self.pending_interrupt

        if time > self.time_slice or time == -1:
            time = self.time_slice
            return True, time

        return False, time

    def update_time(self, interrupt, time):
        """Update the time and check if interrupt happens.

        The arguments should come from :func:`calc_time`,
        they indicate whether an interrupt should be triggered and
        how much time should pass.

        The functions are separated for logging reasons.
        """
        assert not self.pending_interrupt
        if interrupt:
            self.pending_interrupt = True
        self.current_time += time
        self.time_slice -= time

    def switch_module(self, module):
        """Switch context to another :class:`Module`.

        Returns the time taken for the switch.
        """
        if self.pending_interrupt:
            return 0
        return self.context.switch_module(module)

    def yield_module(self, module):
        """Prepare for context switch to the parent :class:`Module`."""
        self.context.yield_module(module)

    def switch_thread(self, thread):
        """Switch context to another :class:`Thread`.

        Returns the time taken for the switch.
        """
        if self.pending_interrupt:
            return 0
        return self.context.switch_thread(thread)

    def crunch(self, thread, time):
        """Simulate being busy for time.

        Being busy will be interrupted if the time slice runs out.

        Returns the time taken executed.
        """
        if self.pending_interrupt:
            return 0
        if self.context.thread != thread:
            raise RuntimeError('forgot to switch_thread')

        interrupted, time = self.calc_time(time)

        self.cpu.log.thread_execute(self.cpu, time)

        self.update_time(interrupted, time)
        self.stats.crunch_time += time

        if interrupted:
            self.context.interrupt()
        else:
            self.cpu.log.thread_yield(self.cpu)
            if self.time_slice == 0:
                self.pending_interrupt = True
        self.context.thread = None

        return time

    #TODO: crunch_module for schedulers

    def finish_step(self, kernel):
        """Finish the time slice.

        Will idle if necessary.
        """
        if not self.pending_interrupt:
            self.cpu.log.cpu_idle(self.cpu, self.time_slice)
        self.pending_interrupt = False
        self.update_time(False, self.time_slice)
        self.stats.idle_time += self.time_slice

        module = self.context.module
        if not module:
            self.context.module = self.context.module_int
        self.cpu.log.timer_interrupt(self.cpu)
        self.context.module = module

        self.time_slice = self.cpu.timer_quantum

        if self.context.module != kernel:
            self.switch_module(kernel)

class Core:
    """A CPU Core.

    The Core has:
        * a unique ID
        * the timer quantum
        * the :class:`_Status`
        * a log to report its actions to

    Apart from the statistics the values are not expected to change much
    during operation.
    """
    def __init__(self, uid, timer_quantum, kernel, log):
        """Create a :class:`Core`."""
        self.uid = uid
        self.timer_quantum = timer_quantum

        self.log = log

        self.status = _Status(self, _Context(self, kernel))

    def switch_module(self, module):
        """See :func:`CoreStatus.switch_module`."""
        return self.status.switch_module(module)

    def yield_module(self, module):
        """See :func:`CoreStatus.yield_module`."""
        self.status.yield_module(module)

    def switch_thread(self, thread):
        """See :func:`CoreStatus.switch_thread`."""
        return self.status.switch_thread(thread)

    def crunch(self, thread, time):
        """See :func:`CoreStatus.crunch`."""
        return self.status.crunch(thread, time)

    def finish_step(self, kernel):
        """See :func:`CoreStatus.finish_step`."""
        self.status.finish_step(kernel)
