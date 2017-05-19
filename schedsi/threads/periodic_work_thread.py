"""Define the :class:`PeriodicWorkThread`."""

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

    def ideal_activations(self, current_time):
        """Return ideal number of activations at `current_time`."""
        return int((current_time - self.original_ready_time) / self.period) + 1

    def _update_ready_time(self, current_time):
        """Update :attr:`ready_time` if the current burst is finished.

        Requires :attr:`current_burst_left` to be up-to-date.
        """
        assert current_time >= self.original_ready_time
        act_actual = self.stats.total_run / self.burst

        if self.ideal_activations(current_time) != act_actual:
            assert (self.ready_time is None and self.remaining == 0) \
                or self.ready_time <= current_time
        else:
            self.ready_time = int(act_actual) * self.period + self.original_ready_time

    # will run as long as the summed up bursts require
    def execute(self):
        """Simulate execution.

        See :meth:`Thread.execute`.
        """
        locked = self.is_running.acquire(False)
        assert locked

        current_time = yield cpurequest.Request.current_time()
        while True:
            assert current_time >= self.original_ready_time

            def act_ideal_in(delta):
                """Return ideal number of activations after `delta` units."""
                return self.ideal_activations(current_time + delta)

            ideal_run_time = act_ideal_in(0) * self.burst
            if self.stats.total_run > ideal_run_time:
                raise RuntimeError('Executed too much')

            quota = 0
            # loop until ideal_run_time no longer increases
            while self.stats.total_run + quota < ideal_run_time:
                quota = ideal_run_time - self.stats.total_run
                ideal_run_time = act_ideal_in(quota) * self.burst

            if quota == 0:
                current_time = yield cpurequest.Request.idle()
                continue

            if self.remaining is not None:
                quota = min(self.remaining, quota)

            current_time = yield from super()._execute(current_time, quota)

    def run_crunch(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run`.
        """
        super().run_crunch(current_time, run_time)
        self._update_ready_time(current_time)
