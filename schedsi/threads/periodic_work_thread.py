"""Define the :class:`PeriodicWorkThread`."""

import math
from schedsi.cpu import request as cpurequest
from schedsi.threads.thread import Thread


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
        if self.remaining is not None:
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
                # FIXME: this is a crutch resulting from floating point inaccuracies
                assert math.isclose(self.current_burst_left, 0, abs_tol=1e-10)
                quota_left = self.current_burst_left

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
