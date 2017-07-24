"""Define the :class:`SchedulerThread`."""

from schedsi.threads._bg_stat_thread import _BGStatThread
from schedsi.cpu import request as cpurequest


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
        scheduler_ready_time = [None]

        scheduler = self._scheduler.schedule(bg_time, scheduler_ready_time)
        request = next(scheduler)
        self._update_ready_time((yield cpurequest.Request.current_time()))
        while True:
            self.last_bg_time = 0

            if request.rtype == cpurequest.Type.idle:
                if scheduler_ready_time[0] is not None:
                    self.ready_time = scheduler_ready_time[0]
                else:
                    self.remaining = 0
                    self.end()

            answer = yield request

            bg_time[0] = self.last_bg_time
            request = scheduler.send(answer)

    def run_background(self, current_time, run_time):
        """Update runtime state.

        See :meth:`Thread.run_background`.
        """
        self.last_bg_time += run_time
        super().run_background(current_time, run_time)

    def num_threads(self):
        """Return number of threads in :attr:`_scheduler`."""
        return self._scheduler.num_threads()

    def all_threads(self):
        """Return a generator yielding every thread of the contained :class:`Scheduler`."""
        return self._scheduler.all_threads()

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
