"""Define the :class:`Thread`."""

import threading
from schedsi.cpu import request as cpurequest


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
