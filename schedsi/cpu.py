#!/usr/bin/env python3
"""Defines a :class:`Core`."""

from schedsi import context, cpurequest

CTXSW_COST = 1

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
        * a :class:`context.Chain`
        * the current time slice (or what's left of it)
        * the current time
        * :class:`_TimeStats`
        * :class:`_ContextSwitchStats`
    """

    def __init__(self, cpu, chain):
        """Create a :class:`_Status`."""
        self.cpu = cpu
        self.chain = chain
        self.prev_chain = None
        self.current_time = 0
        self.stats = _TimeStats()
        self.ctxsw_stats = _ContextSwitchStats()

    def _calc_runtime(self, time):
        """Calculate the execution time available.

        If :attr:`chain.next_timeout` is sooner, then the operation
        would be interrupted. This function evaluates this.

        -1 is considered "as long as possible".

        Also see :meth:`_update_time`.

        Returns how long the current :attr:`chain.next_timeout` allows execution for.
        """
        timeout = self.chain.next_timeout
        if timeout is None:
            if time == -1:
                raise RuntimeError('CPU hang due to unyielding execution without set timer.')
        elif time > timeout or time == -1:
            time = max(0, timeout)

        assert time > 0 or time == 0 and timeout <= 0
        return time

    def _update_time(self, time):
        """Update the time and check if interrupt happens.

        `time` must not be negative.
        """
        assert time > 0
        timeout = self.chain.next_timeout
        if not timeout is None:
            assert time <= timeout or timeout <= 0

        self.current_time += time
        self.chain.elapse(time)

    def _run_background(self, time):
        """Call :meth:`context.Chain.run_background <schedsi.context.Chain.run_background>`
        on :attr:`chain`.
        """
        self.chain.run_background(self.current_time, time)

    def _timer_interrupt(self):
        """Call when :attr:`chain.next_timeout` arrives.

        Resets the timer and jumps back to the kernel.
        """
        assert self.chain.next_timeout <= 0

        self.cpu.log.timer_interrupt(self.cpu, -self.chain.next_timeout)
        self.stats.timer_delay += -self.chain.next_timeout

        idx = self.chain.find_elapsed_timer()
        assert idx == 0
        new_top = self.chain.thread_at(idx)

        time = self._context_switch(new_top)
        self.stats.timer_delay += time
        self.chain.top.run_ctxsw(self.current_time, time)

        prev_chain = self.chain.split(idx + 1)
        prev_chain.finish(self.current_time)

        self.chain.set_timer(None)
        assert len(self.chain) == 1
        self.chain.current_context.restart(self.current_time)

    def _context_switch(self, thread):
        """Perform a context switch.

        The caller is responsible for modifying the context :attr:`chain`
        and call :meth:`Thread.run_ctxsw` on the appropriate :class:`Thread`.

        Returns the context switching time.
        """
        if thread.module == self.chain.top.module:
            self.cpu.log.context_switch(self.cpu, thread, 0)
            #self.ctxsw_stats.thread_time += 0
            return 0

        self.cpu.log.context_switch(self.cpu, thread, CTXSW_COST)
        self.ctxsw_stats.module_time += CTXSW_COST

        time = self._calc_runtime(CTXSW_COST)
        self._update_time(CTXSW_COST)
        assert time == CTXSW_COST or self.chain.next_timeout <= 0

        return CTXSW_COST

    def _switch_to_parent(self):
        """Return execution to the parent :class:`Thread`."""
        if len(self.chain) == 1:
            #kernel yields
            slice_left = self.chian.next_timeout
            self.cpu.log.cpu_idle(self.cpu, slice_left)
            self.stats.idle_time += slice_left
            self._update_time(slice_left)
        else:
            time = self._context_switch(self.chain.parent)
            #who should get this time?
            self.chain.top.run_ctxsw(self.current_time, time)
            prev_chain = self.chain.split(-1)
            self._run_background(time)
            assert len(prev_chain) == 1
            prev_chain.finish(self.current_time)
            self.chain.current_context.reply(context.Chain.from_thread(prev_chain.bottom))

    def _append_chain(self, tail):
        """Continue execution of another :class:`Thread`.

        The thread must be of either the same :class:`Module` or a child :class:`Module`.
        """
        current_thread = self.chain.top
        tail_bottom = tail.bottom
        if not current_thread.module in [tail_bottom.module, tail_bottom.module.parent]:
            raise RuntimeError('Switching thread to unrelated module')
        time = self._context_switch(tail.top)
        #who should get this time?
        current_thread.run_ctxsw(self.current_time, time)
        self._run_background(time)
        self.chain.append_chain(tail)

    def execute(self):
        """Execute one step.

        One step is anything that takes time or switching context.
        """
        #For multi-core emulation this should become a coroutine.
        #It should yield whenever current_time is updated.

        if not self.chain.next_timeout is None and self.chain.next_timeout <= 0:
            self._timer_interrupt()
            return

        while True:
            next_step = self.chain.current_context.execute(self.current_time)
            if next_step.rtype == cpurequest.Type.current_time:
                #no-op
                continue
            elif next_step.rtype == cpurequest.Type.execute:
                time = self._calc_runtime(next_step.thing)
                assert time > 0 and time <= next_step.thing
                self.cpu.log.thread_execute(self.cpu, time)
                self._update_time(time)
                self.stats.crunch_time += time
                self._run_background(time)
                self.chain.top.run_crunch(self.current_time, time)
            elif next_step.rtype == cpurequest.Type.idle:
                self.cpu.log.thread_yield(self.cpu)
                self._switch_to_parent()
                break
            elif next_step.rtype == cpurequest.Type.resume_chain:
                assert len(next_step.thing) == 1
                chain = context.Chain.from_thread(next_step.thing.bottom)
                self._append_chain(chain)
            elif next_step.rtype == cpurequest.Type.timer:
                if self.chain.top.module != self.cpu.kernel:
                    raise RuntimeError('Received timer request from non-kernel scheduler.')
                self.chain.set_timer(next_step.thing)
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

    def __init__(self, uid, init_thread, log):
        """Create a :class:`Core`."""
        self.uid = uid

        self.log = log

        self.status = _Status(self, context.Chain.from_thread(init_thread))

        log.init_core(self)

    def execute(self):
        """Execute one step.

        See :meth:`_Status.execute`.
        """
        self.status.execute()

    def get_statistics(self):
        """Obtain statistics."""
        stats = self.status.stats.__dict__.copy()
        stats.update(self.status.ctxsw_stats.__dict__)
        return stats

    @property
    def kernel(self):
        """The Kernel module."""
        return self.status.chain.bottom.module
