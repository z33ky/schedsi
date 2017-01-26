#!/usr/bin/env python3
"""Defines a :class:`Core`."""

from schedsi import context, cpurequest

CTXSW_COST = 1


class _ContextSwitchStats:  # pylint: disable=too-few-public-methods
    """Context switching statistics."""

    def __init__(self):
        """Create a :class:`_ContextSwitchStats`."""
        self.thread_time = 0
        self.module_time = 0


class _TimeStats:  # pylint: disable=too-few-public-methods
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
        if time == 0:
            return 0

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
        assert time >= 0
        timeout = self.chain.next_timeout
        if timeout is not None:
            assert time <= timeout or timeout <= 0

        self.current_time += time
        self.chain.elapse(time)

    def _run_background(self, time):
        """Call :meth:`context.Chain.run_background <schedsi.context.Chain.run_background>` \
        on :attr:`chain`.
        """
        self.chain.run_background(self.current_time, time)

    def _timer_interrupt(self):
        """Call when :attr:`chain.next_timeout` arrives.

        Resets the timer and jumps back to the kernel.
        """
        assert self.chain.next_timeout <= 0

        idx = self.chain.find_elapsed_timer()
        self.cpu.log.timer_interrupt(self.cpu, idx, -self.chain.next_timeout)
        self.stats.timer_delay += -self.chain.next_timeout

        _, time = self._context_switch(split_index=idx)
        self.stats.timer_delay += time

        self.chain.set_timer(None)

    def _context_switch(self, *, split_index=None, appendix=None):
        """Perform a context switch.

        The destination is specified by `split_index`, an index into the context :attr:`chain`,
        or by `appendix`, a :class:`context.Chain <schedsi.context.Chain>` to append.
        Specifying both is an error.

        If `split_index` is set, also send the previous chain to the switched-to context via
        :meth:`Context.reply <schedsi.context.Context.reply>`.

        Returns a tuple (previous chain, context switch cost).
        The previous chain is the tail of the context :attr:`chain` that is cut off
        when `split_index` is set. It is `None` if `split_index` is `None`.
        """
        if split_index is not None:
            assert appendix is None
            assert split_index != -1
        else:
            assert appendix is not None
            assert len(appendix) != 0

        thread_from = self.chain.current_context.thread
        thread_to = appendix and appendix.top or self.chain.thread_at(split_index)

        if thread_to.module == thread_from.module:
            cost = 0
            self.ctxsw_stats.thread_time += cost
        else:
            cost = CTXSW_COST
            self.ctxsw_stats.module_time += cost

        self.cpu.log.context_switch(self.cpu, split_index, appendix, cost)

        prev_chain = None
        if split_index is not None:
            prev_chain = self.chain.split(split_index + 1)
            self.chain.current_context.reply(prev_chain)

        # update for cost regardless of the time-slice, because context switching is atomic
        self._update_time(cost)
        assert self._calc_runtime(cost) == cost or self.chain.next_timeout <= 0

        thread_from.run_ctxsw(self.current_time, cost)
        self._run_background(cost)

        if appendix is not None:
            self.chain.append_chain(appendix)

        assert thread_from != self.chain.top

        return prev_chain, cost

    def _switch_to_parent(self):
        """Return execution to the parent :class:`Thread`."""
        if len(self.chain) == 1:
            # kernel yields
            slice_left = self.chian.next_timeout
            if slice_left <= 0:
                raise RuntimeError('Kernel cannot yield without timeout.')
            self.cpu.log.cpu_idle(self.cpu, slice_left)
            self.stats.idle_time += slice_left
            self._update_time(slice_left)
        else:
            prev_chain, _ = self._context_switch(split_index=-2)
            assert len(prev_chain) == 1

    def _append_chain(self, tail):
        """Continue execution of another :class:`Thread`.

        The thread must be of either the same :class:`Module` or a child :class:`Module`.
        """
        prev_thread = self.chain.top
        if prev_thread.module not in (tail.bottom.module, tail.bottom.module.parent):
            raise RuntimeError('Switching thread to unrelated module')
        prev_chain, _ = self._context_switch(appendix=tail)
        assert prev_chain is None

    def _handle_request(self, request):
        """Handle a :class:`~schedsi.cpurequest.Request`.

        Returns whether time was spent handling the request..
        """
        if request.rtype == cpurequest.Type.current_time:
            # no-op
            return False
        elif request.rtype == cpurequest.Type.execute:
            time = self._calc_runtime(request.thing)
            assert time > 0
            assert time <= request.thing or request.thing == -1
            self.cpu.log.thread_execute(self.cpu, time)
            self._update_time(time)
            self.stats.crunch_time += time
            self._run_background(time)
            self.chain.top.run_crunch(self.current_time, time)
        elif request.rtype == cpurequest.Type.idle:
            self.cpu.log.thread_yield(self.cpu)
            self._switch_to_parent()
        elif request.rtype == cpurequest.Type.resume_chain:
            self._append_chain(request.thing)
        elif request.rtype == cpurequest.Type.timer:
            self.chain.set_timer(request.thing)
            return False
        else:
            assert False
        return True

    def execute(self):
        """Execute one step.

        One step is anything that takes time or switching context.
        """
        # For multi-core emulation this should become a coroutine.
        # It should yield whenever current_time is updated.

        if self.chain.next_timeout is not None and self.chain.next_timeout <= 0:
            self._timer_interrupt()
            return

        while not self._handle_request(self.chain.current_context.execute(self.current_time)):
            pass


class _KernelTimerOnlyStatus(_Status):
    """Status of a CPU Core allowing only the kernel to have timers."""

    def _timer_interrupt(self):
        """See :meth:`_Status._timer_interrupt`.

        Ensures only the kernel receives the interrupt
        and restarts the kernel scheduler.
        """
        super()._timer_interrupt()

        # only kernel timer may interrupt
        assert len(self.chain) == 1

        # kernel scheduler gets restarted
        current_context = self.chain.current_context
        current_context.buffer.finish(self.current_time)
        current_context.reply(None)
        current_context.restart(self.current_time)

    def _switch_to_parent(self):
        """See :meth:`_Status._switch_to_parent`.

        Breaks the previous :class:`context.Chain <schedsi.context.Chain>`
        to let it be rebuild.
        """
        super()._switch_to_parent()
        current_context = self.chain.current_context
        prev_chain = current_context.buffer
        if prev_chain is not None:
            prev_chain.finish(self.current_time)
            current_context.reply(None)
            current_context.reply(context.Chain.from_thread(prev_chain.bottom))

    def _handle_request(self, request):
        """See :meth:`_Status._handle_request`.

        Ensures that

            * only :class:`context.Chains <schedsi.context.Chain>` of length 1
              can be resumed and restarts that one thread
            * only the kernel can set a timer.

        """
        if request.rtype == cpurequest.Type.resume_chain:
            assert len(request.thing) == 1
            chain = context.Chain.from_thread(request.thing.bottom)
            self._append_chain(chain)
            return True
        if request.rtype == cpurequest.Type.timer:
            if self.chain.top.module != self.cpu.kernel:
                if request.thing is None:
                    return False
                raise RuntimeError('Received timer request from non-kernel scheduler.')
            # let super() handle the rest of this request
        return super()._handle_request(request)


class Core:
    """A CPU Core.

    The Core has:
        * a unique ID
        * the timer quantum
        * a log to report its actions to
        * the :class:`_Status`

    The values are not expected to change much during operation.
    """

    def __init__(self, uid, init_thread, log, *, local_timer_scheduling):
        """Create a :class:`Core`."""
        self.uid = uid

        self.log = log

        status_class = _Status if local_timer_scheduling else _KernelTimerOnlyStatus
        self.status = status_class(self, context.Chain.from_thread(init_thread))

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
