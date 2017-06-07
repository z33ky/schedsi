"""Define the :class:`_BGStatThread`.

This should be used in favor of :class:`Thread` for non-worker threads.
"""

from schedsi.threads.thread import Thread
import sys


class _BGStatThread(Thread):
    """Base class for threads recording background time."""

    def __init__(self, module, tid=None, **kwargs):
        """Create a :class:`_BGStatThread`."""
        super().__init__(module, tid=tid, **kwargs)
        if tid is None:
            print('Warning: Did not specify tid for non-worker thread', self.module.name, self.tid,
                  '. Usually automatic naming is not desired here.', file=sys.stderr)

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
