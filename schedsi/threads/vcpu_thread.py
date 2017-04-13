"""Define the :class:`VCPUThread`."""

import sys
from schedsi.threads._bg_stat_thread import _BGStatThread
from schedsi.threads.scheduler_thread import SchedulerThread
from schedsi.cpu import context, request as cpurequest


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

        super().__init__(module, *args, **kwargs,
                         ready_time=self._thread.ready_time, units=self._thread.remaining)

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
            self._update_ready_time(current_time)
            self._chain = yield cpurequest.Request.resume_chain(self._chain)
            current_time = yield cpurequest.Request.current_time()
            if self._thread.ready_time > current_time:
                current_time = yield cpurequest.Request.idle()

    def suspend(self, current_time):
        """Become suspended.

        See :meth:`Thread.suspend`.
        """
        super().suspend(current_time)
        self.ready_time = self._thread.ready_time
        self.remaining = self._thread.remaining

    def get_statistics(self, current_time):
        """Obtain statistics.

        See :meth:`_BGStatThread.get_statistics`.
        """
        stats = super().get_statistics(current_time)
        sched_key = (self._thread.module.name, self._thread.tid)
        stats['scheduler'] = {sched_key: self._thread.get_statistics(current_time)}
        return stats
