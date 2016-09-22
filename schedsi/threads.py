#!/usr/bin/env python3
"""Thread classes."""

import numbers
import sys
import threading

class _ThreadStats: # pylint: disable=too-few-public-methods
    """Thread statistics."""

    def __init__(self):
        """Create a :class:`_ThreadStats`."""
        self.finished_time = -1
        self.ctxsw_times = []
        self.run_times = []
        self.wait_times = []

class Thread:
    """The basic thread class.

    A thread has
        * an associated module
        * a locally unique thread id
        * ready time (-1 if finished)
        * remaining workload (-1 if infinite)
        * a lock indicating whether this thread is currently active
        * :class:`_ThreadStats`
    """

    def __init__(self, module, tid=None, *, ready_time=0, units=-1):
        """Create a :class:`Thread`."""
        self.module = module
        if tid is None:
            tid = module.num_threads()
        self.tid = tid
        self.ready_time = ready_time
        self.remaining = units
        self.is_running = threading.Lock()
        self.stats = _ThreadStats()

    def execute(self):
        """Simulate execution.

        The thread will run for as long as it can.

        Yields the amount of time it wants to execute,
        -1 for infinite and 0 to indicate the desire to yield,
        or a thread to switch to. None for no-op.
        Consumes the current time.
        """
        self.is_running.acquire(False)
        assert self.is_running.locked

        current_time = yield
        while True:
            current_time = yield from self._execute(current_time, -1)

    def _execute(self, current_time, run_time):
        """Simulate execution.

        Update some state.
        Yields `run_time` respecting :attr:`remaining`, so it won't
        yield more than that.

        Returns the next current time or None if :attr:`remaining` is 0.
        """
        assert self.ready_time != -1 and self.ready_time <= current_time
        assert self.remaining != 0
        assert self.is_running.locked

        self.stats.wait_times.append(current_time - self.ready_time)
        self.ready_time = current_time

        if run_time == -1:
            run_time = self.remaining
        else:
            assert run_time <= self.remaining or self.remaining == -1

        current_time = yield run_time

        if self.remaining == 0:
            yield 0
            return

        return current_time

    def run_ctxsw(self, current_time, run_time):
        pass

    def run_background(self, current_time, run_time):
        assert self.is_running.locked
        self.ready_time = current_time

    def run_crunch(self, current_time, run_time):
        """Update runtime state.

        This should be called while the thread is active.
        `current_time` refers to the time just after this thread has run.
        """
        assert self.is_running.locked

        self.stats.run_times.append(run_time)

        #assert self.ready_time + run_time == current_time
        self.ready_time = current_time

        if self.remaining != -1:
            assert self.remaining >= run_time
            self.remaining -= run_time

            if self.remaining == 0:
                #the job was completed within the slice
                self.stats.finished_time = self.ready_time
                #never start again
                self.ready_time = -1

    def finish(self, current_time):
        """Become inactive.

        This should be called when the thread becomes inactive.
        """
        assert self.is_running.locked
        self.is_running.release()

class _BGStatThread(Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bg_times = []

    def run_background(self, current_time, run_time):
        self.bg_times.append(run_time)
        super().run_background(current_time, run_time)

class SchedulerThread(_BGStatThread):
    """A thread representing a VCPU for a child.

    Execution is forwarded to the scheduler of the child :class:`Module`.
    """

    def __init__(self, *args, scheduler, **kwargs):
        """Create a :class:`SchedulerThread`."""
        super().__init__(scheduler.module, *args, **kwargs)
        self._scheduler = scheduler
        self.next_ready_time = None

    def execute(self):
        """Simulate execution.

        Simply forward to the scheduler.

        See :meth:`Thread.execute`.
        """
        self.is_running.acquire(False)
        assert self.is_running.locked

        scheduler = self._scheduler.schedule()
        thing = next(scheduler)
        assert thing is None
        current_time = yield

        while True:
            assert self.next_ready_time is None

            null = next(super()._execute(current_time, 0))
            assert null == 0
            thing = scheduler.send(current_time)
            if isinstance(thing, numbers.Integral):
                if thing == 0:
                    #scheduler has no more threads
                    self.next_ready_time = -1
                else:
                    #scheduler only has waiting threads
                    self.next_ready_time = thing
                    thing = 0

            current_time = yield thing

    def run(self, current_time, run_time):
        if self.next_ready_time == -1:
            #only the kernel scheduler should be invoked while idle
            assert self.module.parent is None
            self.next_ready_time = current_time - run_time
        super().run(current_time, run_time)

    def finish(self, current_time):
        """Become inactive.

        See :meth:`Thread.finish`.
        """
        if not self.next_ready_time is None:
            #scheduler yielded, we'll want to wait a bit
            self.ready_time = self.next_ready_time

            if self.ready_time == -1:
                self.remaining = 0
            else:
                assert self.remaining != 0
                assert self.ready_time >= current_time

            self.next_ready_time = None

        super().finish(current_time)

    def num_threads(self):
        return self._scheduler.num_threads()

    def add_threads(self, new_threads):
        """Add threads to scheduler."""
        self._scheduler.add_threads(new_threads)

class VCPUThread(_BGStatThread):
    """A thread representing a VCPU from the perspective of a parent.

    Execution is forwarded to the :class:`SchedulerThread` of the child.
    """

    def __init__(self, module, *args, child, **kwargs):
        """Create a :class:`VCPUThread`."""
        if child.parent != module:
            print(module.name, "is adding a VCPUThread for", child.name,
                  "although it is not a direct descendant.", file=sys.stderr)
        self._thread = child.register_vcpu(self)
        if not isinstance(self._thread, SchedulerThread):
            print("VCPUThread expected a SchedulerThread, got", type(self._thread).__name__, ".",
                  file=sys.stderr)

        super().__init__(module, *args, **kwargs, ready_time=self._thread.ready_time, units=None)

        self._update_active = False

    def execute(self):
        """Simulate execution.

        Switch context and forward to child thread.

        See :meth:`Thread.execute`.
        """
        self.is_running.acquire(False)
        assert self.is_running.locked

        current_time = yield
        while True:
            self._update_active = True
            if self._thread.ready_time > self.ready_time:
                self.ready_time = self._thread.ready_time
            if self.ready_time > current_time:
                self._update_active = False
                yield 0
            if self._thread.remaining == 0:
                assert self._thread.ready_time == -1
                self.ready_time = -1
                self._update_active = False
                yield 0
            null = next(super()._execute(current_time, 0))
            assert null == 0
            self._update_active = False
            current_time = yield self._thread

    def run_crunch(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run`.
        """
        self._update_active = True
        super().run_crunch(current_time, run_time)
        self._update_active = False

    def __getattribute__(self, key):
        """:attr:`ready_time` and :attr:`remaining` should be taken from the
        :class:`SchedulerThread`.

        Except for ready_time when we're calculating this thread's statistics,
        for which `_update_active` should be set so the key is passed through.
        """
        if key == 'remaining' or (key == 'ready_time' and
                                  not object.__getattribute__(self, '_update_active')):
            return object.__getattribute__(self, '_thread').__getattribute__(key)
        return object.__getattribute__(self, key)

class PeriodicWorkThread(Thread):
    """A thread needing periodic bursts of CPU."""

    def __init__(self, module, *args, period, burst, **kwargs):
        """Create a :class:`PeriodicWorkThread`."""
        if period < burst:
            raise RuntimeError('burst must not exceed period')
        if period <= 0:
            raise RuntimeError('period must be > 0')
        super().__init__(module, *args, **kwargs)
        self.original_ready_time = self.ready_time
        self.period = period
        self.burst = burst
        self.current_burst_left = None
        self.total_run_time = 0

    def _calc_activations(self, current_time):
        """Calculate the number activations at `current_time`."""
        return int((current_time - self.original_ready_time) / self.period) + 1

    def _get_quota(self, current_time):
        """Calculate the quota at `current_time`.

        Won't return more than :attr:`remaining`.
        """
        quota_left = self._calc_activations(current_time) * self.burst - self.total_run_time
        if self.remaining != -1:
            quota_left = min(self.remaining, quota_left)
        return quota_left

    def _update_ready_time(self, current_time):
        """Update :attr:`ready_time` if the current burst is finished.

        Requires :attr:`current_burst_left` to be up-to-date.
        """
        assert not self.current_burst_left is None
        if self.current_burst_left == 0:
            self.ready_time = self._calc_activations(current_time) * self.period \
                            + self.original_ready_time

    #will run as long as the summed up bursts require
    def execute(self):
        """Simulate execution.

        See :meth:`Thread.execute`.
        """
        self.is_running.acquire(False)
        assert self.is_running.locked

        current_time = yield
        while True:
            quota_left = self._get_quota(current_time)
            if quota_left != 0:
                if quota_left < 0:
                    raise RuntimeError('Executed too much')
                quota_plus = self._get_quota(current_time + quota_left)
                #TODO: be smarter
                while quota_plus > quota_left:
                    quota_left = quota_plus
                    quota_plus = self._get_quota(current_time + quota_left)
                self.current_burst_left = quota_left
            else:
                self.current_burst_left = 0

            current_time = yield from super()._execute(current_time, quota_left)
            if self.current_burst_left == 0:
                yield 0
                return

    def run_crunch(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run`.
        """
        super().run_crunch(current_time, run_time)
        assert self.current_burst_left >= run_time
        self.current_burst_left -= run_time
        self._update_ready_time(current_time)
        self.total_run_time += run_time
        assert self.total_run_time == sum(self.stats.run_times)

    def finish(self, current_time):
        """Become inactive.

        See :meth:`Thread.finish`.
        """
        self._update_ready_time(current_time)
        self.current_burst_left = None
        super().finish(current_time)
