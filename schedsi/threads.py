#!/usr/bin/env python3
"""Thread classes."""

import sys
import threading

class _ThreadStats: # pylint: disable=too-few-public-methods
    """Thread statistics."""

    def __init__(self):
        """Create a :class:`_ThreadStats`."""
        self.finished_time = -1
        self.total_run_time = 0
        self.total_wait_time = 0

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

    def __init__(self, module, tid, *, ready_time=0, units=-1):
        """Create a :class:`Thread`."""
        self.module = module
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
        locked = self.is_running.acquire(False)
        assert locked

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
        assert not self.is_running.acquire(False)
        self.stats.total_wait_time += current_time - self.ready_time

        if run_time == -1:
            run_time = self.remaining
        else:
            assert run_time <= self.remaining or self.remaining == -1

        current_time = yield run_time

        if self.remaining == 0:
            yield 0
            return

        return current_time

    def run(self, _current_time, run_time):
        """Update runtime state.

        This should be called while the thread is active.
        """
        assert not self.is_running.acquire(False)
        self.stats.total_run_time += run_time

        if self.remaining != -1:
            assert self.remaining >= run_time
            self.remaining -= run_time

    def finish(self, current_time):
        """Become inactive.

        This should be called when the thread becomes inactive.
        """
        assert not self.is_running.acquire(False)
        self._finish(current_time)

        self.is_running.release()

    def _finish(self, current_time):
        assert not self.is_running.acquire(False)

        if self.remaining == 0:
            #the job was completed within the slice
            #never start again
            self.ready_time = -1
            self.stats.finished_time = current_time
        elif self.remaining != -1:
            #not enough time to complete the job
            self.ready_time = current_time

class SchedulerThread(Thread):
    """A thread representing a VCPU for a child.

    Execution is forwarded to the scheduler of the child :class:`Module`.
    """

    def __init__(self, *args, scheduler, **kwargs):
        """Create a :class:`SchedulerThread`."""
        super().__init__(scheduler.module, *args, **kwargs)
        self._scheduler = scheduler

    def execute(self):
        """Simulate execution.

        Simply forward to the scheduler.

        See :meth:`Thread.execute`.
        """
        locked = self.is_running.acquire(False)
        assert locked

        scheduler = self._scheduler.schedule()
        thing = next(scheduler)
        assert thing is None
        current_time = yield
        while True:
            next(super()._execute(current_time, -1))
            current_time = yield scheduler.send(current_time)

    def num_threads(self):
        return self._scheduler.num_threads()

    def add_threads(self, new_threads):
        """Add threads to scheduler."""
        self._scheduler.add_threads(new_threads)

class VCPUThread(Thread):
    """A thread representing a VCPU from the perspective of a parent.

    Execution is forwarded to the :class:`SchedulerThread` of the child.
    """

    def __init__(self, module, *args, child, **kwargs):
        """Create a :class:`VCPUThread`."""
        if child.parent != module:
            print(module.name, "is adding a VCPUThread for", child.name,
                  "although it is not a direct descendant.", file=sys.stderr)
        super().__init__(module, *args, **kwargs, ready_time=None, units=None)
        self._thread = child.register_vcpu(self)
        if not isinstance(self._thread, SchedulerThread):
            print("VCPUThread expected a SchedulerThread, got", type(self._thread).__name__, ".",
                  file=sys.stderr)

    def execute(self):
        """Simulate execution.

        Switch context and forward to child thread.

        See :meth:`Thread.execute`.
        """
        locked = self.is_running.acquire(False)
        assert locked

        current_time = yield
        while True:
            next(super()._execute(current_time, -1))
            current_time = yield self._thread

    def __getattribute__(self, key):
        """ready_time and remaining should be taken from the :class:`SchedulerThread`."""
        if key in ['ready_time', 'remaining']:
            return self._thread.__getattribute__(key)
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
        self.burst_started = None

    def _get_quota(self, current_time):
        """Calculate the quote at `current_time`.

        Won't return more than :attr:`remaining`.
        """
        activations = int((current_time - self.original_ready_time) / self.period) + 1
        quota = activations * self.burst
        if self.remaining != -1:
            quota = min(self.remaining + self.stats.total_run_time, quota)
        return quota

    #will run as long as the summed up bursts require
    def execute(self):
        """Simulate execution.

        See :meth:`Thread.execute`.
        """
        locked = self.is_running.acquire(False)
        assert locked

        current_time = yield
        while True:
            quota = self._get_quota(current_time)
            if quota < 0:
                raise RuntimeError('Scheduled too eagerly')
            quota_left = quota - self.stats.total_run_time
            if quota_left < 0:
                raise RuntimeError('Executed too much')
            quota_plus = self._get_quota(current_time + quota_left) - self.stats.total_run_time
            self.burst_started = current_time - self.original_ready_time
            #TODO: be smarter
            while quota_plus > quota_left:
                quota_left = quota_plus
                quota_plus = self._get_quota(current_time + quota_left) - self.stats.total_run_time
                self.burst_started += self.period
            self.current_burst_left = quota_left

            current_time = yield from super()._execute(current_time, quota_left)

    def run(self, current_time, run_time):
        """See :meth:`Thread.run`."""
        super().run(current_time, run_time)
        assert self.current_burst_left >= run_time
        self.current_burst_left -= run_time

    def _finish(self, current_time):
        super()._finish(current_time)
        #set ready_time to next burst arrival, if required
        if (self.remaining > 0 or self.remaining == -1) \
           and self.current_burst_left == 0:
            self.ready_time = self.burst_started + self.period
            self.burst_started = None
        self.current_burst_left = None
