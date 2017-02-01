#!/usr/bin/env python3
"""Thread classes."""

import sys
import threading
from schedsi import context, cpurequest


class _ThreadStats:  # pylint: disable=too-few-public-methods
    """Thread statistics."""

    def __init__(self):
        """Create a :class:`_ThreadStats`."""
        self.finished_time = -1
        self.ctxsw = []
        self.run = []
        self.wait = [[]]


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

        Yields a :class:`~schedsi.cpurequest.Request`.
        Consumes the current time.
        """
        locked = self.is_running.acquire(False)
        assert locked

        current_time = yield cpurequest.Request.current_time()
        while True:
            current_time = yield from self._execute(current_time, -1)

    def _update_ready_time(self, current_time):
        """Update ready_time while executing.

        Includes some checks to make sure the state is sane.
        """
        assert self.ready_time != -1 and self.ready_time <= current_time
        assert self.is_running.locked()

        self.ready_time = current_time

    def _execute(self, current_time, run_time):
        """Simulate execution.

        Update some state.
        Yields an execute :class:`~schedsi.cpurequest.Request`
        respecting :attr:`remaining`, so it won't yield more than that.

        Returns the next current time or None if :attr:`remaining` is 0.
        """
        assert not self.is_finished()

        self._update_ready_time(current_time)

        if run_time == -1:
            run_time = self.remaining
        else:
            assert run_time > 0
            assert run_time <= self.remaining or self.remaining == -1

        current_time = yield cpurequest.Request.execute(run_time)

        if self.is_finished():
            yield cpurequest.Request.idle()
            return

        return current_time

    def is_finished(self):
        """Check if the :class:`Thread` is finished.

        Returns True if the :class:`Thread` still has something to do,
        False otherwise.
        """
        return self.remaining == 0

    def run_ctxsw(self, _current_time, run_time):
        """Update runtime state.

        This should be called just after a context switch to another thread
        when this was just the active thread, or when returning to this thread,
        whether the context switch was successful or not.
        `current_time` refers to the time just after the context switch.
        """
        if not self.is_running.locked():
            # this can happen if the thread was just switched to when the timer elapsed
            # and we now switch away from this thread
            locked = self.is_running.acquire(False)
            assert locked
        self.stats.ctxsw.append(run_time)

    def run_background(self, _current_time, _run_time):
        """Update runtime state.

        This should be called while the thread is in the context stack, but not
        active (not the top).
        `_current_time` refers to the time just after the active thread has run.
        """
        assert self.is_running.locked()
        # never called for work threads
        assert False

    def run_crunch(self, current_time, run_time):
        """Update runtime state.

        This should be called while the thread is active.
        `current_time` refers to the time just after this thread has run.
        """
        assert self.is_running.locked()

        self.stats.run[-1].append(run_time)

        self.ready_time += run_time
        assert self.ready_time == current_time

        if self.remaining != -1:
            assert self.remaining >= run_time
            self.remaining -= run_time

            if self.is_finished():
                # the job was completed within the slice
                self.end()
                return

    def end(self):
        """End execution."""
        assert self.is_finished()
        self.stats.finished_time = self.ready_time
        # never start again
        self.ready_time = -1

    def suspend(self, current_time):
        """Become suspended.

        This should be called when the thread becomes inactive,
        but will be resumed later.

        `current_time` refers to the time before the context switch
        away from this thread.
        """
        if self.is_running.locked():
            # only record waiting time if the thread has executed
            self.stats.wait.append([])
            self.ready_time = max(self.ready_time, current_time)

    def resume(self, current_time, returning):
        """Resume execution.

        This should be called after :meth:`suspend` to become active again.

        `current_time` refers to the time just after the context switch.
        """
        if self.is_finished():
            return

        assert self.ready_time != -1

        if returning:
            self._update_ready_time(current_time)
        else:
            if current_time >= self.ready_time:
                # we only want to record waiting time if the thread is ready to execute
                self.stats.wait[-1].append(current_time - self.ready_time)
                self.stats.run.append([])
                # we can't use _update_ready_time() here because we might not yet be executing
                self.ready_time = current_time

    def finish(self, _current_time):
        """Become inactive.

        This should be called when the thread becomes inactive.
        """
        assert self.is_running.locked()
        self.is_running.release()

    def get_statistics(self, current_time):
        """Obtain statistics.

        Not thread-safe.
        """
        # the CPU should be locked during this
        # this means we can read data without locking self.is_running
        stats = self.stats.__dict__.copy()
        if not self.is_finished() and current_time >= self.ready_time:
            assert self.ready_time != -1
            stats['waiting'] = current_time - self.ready_time
        if stats['wait'][-1] == []:
            stats['wait'].pop()
        stats['remaining'] = self.remaining
        return stats


class _BGStatThread(Thread):
    """Base class for threads recording background time."""

    def __init__(self, *args, **kwargs):
        """Create a :class:`_BGStatThread`."""
        super().__init__(*args, **kwargs)
        self.bg_times = [[]]

    def run_background(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run_background`.
        """
        self.bg_times[-1].append(run_time)
        self._update_ready_time(current_time)

    def resume(self, current_time, returning):
        if returning:
            self.bg_times.append([])
        super().resume(current_time, returning)

    def finish(self, current_time):
        """Become inactive.

        See :meth:`Thread.finish`.
        """
        if self.module.parent is not None or self.tid != 0:
            self.bg_times.append([])
        else:
            # in single timer scheduling the kernel is restarted
            # but we already got a new list from resume() after the context switch
            assert self.bg_times[-1] == []
        super().finish(current_time)

    def get_statistics(self, current_time):
        """Obtain statistics.

        See :meth:`Thread.get_statistics`.
        """
        stats = super().get_statistics(current_time)
        stats['bg'] = self.bg_times
        if stats['bg'][-1] == []:
            stats['bg'].pop()
        return stats


class SchedulerThread(_BGStatThread):
    """A thread representing a VCPU for a child.

    Execution is forwarded to the scheduler of the child :class:`Module`.
    """

    def __init__(self, *args, scheduler, **kwargs):
        """Create a :class:`SchedulerThread`."""
        super().__init__(scheduler.module, *args, **kwargs)
        self._scheduler = scheduler
        self.last_bg_time = None

    def execute(self):
        """Simulate execution.

        Simply forward to the scheduler.

        See :meth:`Thread.execute`.
        """
        locked = self.is_running.acquire(False)
        assert locked

        # abusing a list as communication channel
        bg_time = [self.last_bg_time]

        scheduler = self._scheduler.schedule(bg_time)
        thing = next(scheduler)
        current_time = yield cpurequest.Request.current_time()
        self._update_ready_time(current_time)
        while True:
            self.last_bg_time = 0
            current_time = yield thing
            bg_time[0] = self.last_bg_time
            thing = scheduler.send(current_time)

    def run_background(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run_background`.
        """
        self.last_bg_time += run_time
        super().run_background(current_time, run_time)

    def run_ctxsw(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run_ctxsw`.
        """
        super().run_ctxsw(current_time, run_time)

    def num_threads(self):
        """Return number of threads in :attr:`_scheduler`."""
        return self._scheduler.num_threads()

    def add_thread(self, thread, **kwargs):
        """Add threads to scheduler."""
        self._scheduler.add_thread(thread, **kwargs)

    def get_statistics(self, current_time):
        """Obtain statistics.

        See :meth:`_BGStatThread.get_statistics`.
        """
        stats = super().get_statistics(current_time)
        stats['children'] = self._scheduler.get_thread_statistics(current_time)
        return stats


class VCPUThread(_BGStatThread):
    """A thread representing a VCPU from the perspective of a parent.

    Execution is forwarded to the :class:`SchedulerThread` of the child.
    """

    def __init__(self, module, *args, child, **kwargs):
        """Create a :class:`VCPUThread`."""
        if child.parent != module:
            print(module.name, 'is adding a VCPUThread for', child.name,
                  'although it is not a direct descendant.', file=sys.stderr)
        self._chain = context.Chain.from_thread(child.register_vcpu(self))
        if not isinstance(self._chain.bottom, SchedulerThread):
            print('VCPUThread expected a SchedulerThread, got', type(self._thread).__name__, '.',
                  file=sys.stderr)

        super().__init__(module, *args, **kwargs, ready_time=self._thread.ready_time, units=None)

        self._update_active = False

    @property
    def _thread(self):
        """The :class:`Thread` the execution is forwarded to."""
        return self._chain.bottom

    def execute(self):
        """Simulate execution.

        Switch context and forward to child thread.

        See :meth:`Thread.execute`.
        """
        locked = self.is_running.acquire(False)
        assert locked

        current_time = yield cpurequest.Request.current_time()
        while True:
            self._update_active = True
            self._update_ready_time(current_time)
            self._update_active = False
            self._chain = yield cpurequest.Request.resume_chain(self._chain)
            current_time = yield cpurequest.Request.idle()

    def suspend(self, current_time):
        """Become suspended.

        See :meth:`Thread.suspend`.
        """
        self._update_active = True
        super().suspend(current_time)
        self._update_active = False

    def resume(self, current_time, returning):
        """Resume execution.

        See :meth:`_BGStatThread.resume`.
        """
        self._update_active = True
        super().resume(current_time, returning)
        self._update_active = False

    def run_crunch(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run`.
        """
        self._update_active = True
        super().run_crunch(current_time, run_time)
        self._update_active = False

    def get_statistics(self, current_time):
        """Obtain statistics.

        See :meth:`_BGStatThread.get_statistics`.
        """
        stats = super().get_statistics(current_time)
        sched_key = (self._thread.module.name, self._thread.tid)
        stats['scheduler'] = {sched_key: self._thread.get_statistics(current_time)}
        return stats

    def __getattribute__(self, key):
        """:attr:`ready_time` and :attr:`remaining` should be taken from the \
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
        if period <= burst:
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
        assert self.current_burst_left is not None
        if self.current_burst_left == 0:
            self.ready_time = self._calc_activations(current_time) * self.period \
                            + self.original_ready_time

    # will run as long as the summed up bursts require
    def execute(self):
        """Simulate execution.

        See :meth:`Thread.execute`.
        """
        locked = self.is_running.acquire(False)
        assert locked

        current_time = yield cpurequest.Request.current_time()
        while True:
            quota_left = self._get_quota(current_time)
            if quota_left != 0:
                if quota_left < 0:
                    raise RuntimeError('Executed too much')
                quota_plus = self._get_quota(current_time + quota_left)
                # TODO: be smarter
                while quota_plus > quota_left:
                    quota_left = quota_plus
                    quota_plus = self._get_quota(current_time + quota_left)
                self.current_burst_left = quota_left
            else:
                self.current_burst_left = 0

            current_time = yield from super()._execute(current_time, quota_left)
            if self.current_burst_left == 0:
                current_time = yield cpurequest.Request.idle()

    def run_crunch(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run`.
        """
        super().run_crunch(current_time, run_time)
        assert self.current_burst_left >= run_time
        self.current_burst_left -= run_time
        self._update_ready_time(current_time)
        self.total_run_time += run_time
        assert self.total_run_time == sum([sum(x) for x in self.stats.run])

    def finish(self, current_time):
        """Become inactive.

        See :meth:`Thread.finish`.
        """
        self._update_ready_time(current_time)
        self.current_burst_left = None
        super().finish(current_time)
