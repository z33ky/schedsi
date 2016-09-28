#!/usr/bin/env python3
"""Defines a shortest job first scheduler."""

import bisect
from schedsi import scheduler

class SJF(scheduler.Scheduler):
    """Shortest job first scheduler."""

    def __init__(self, module):
        """Create a :class:`SJF` scheduler."""
        super().__init__(module)

    def _update_ready_threads(self, time, rcu_data):
        """See :meth:`Scheduler._update_ready_threads`.

        To make the scheduling decision easier,
        the threads will be sorted by remaining time.
        """
        ready_threads = rcu_data.ready_threads
        finished_threads = rcu_data.finished_threads
        new_idx = len(ready_threads)
        super()._update_ready_threads(time, rcu_data)
        assert rcu_data.last_idx == -1

        new_threads = ready_threads[new_idx:]
        del ready_threads[new_idx:]

        #we sort the list to make insertion easier
        new_threads = sorted(new_threads, key=lambda t: t.remaining)

        #remaining_list should contain the remaining times of all non-infinitly threads
        inf_idx = next((i for i, t in enumerate(ready_threads) if t.remaining == -1), None)
        remaining_list = list(t.remaining for t in ready_threads[:inf_idx])

        #filter out the infinitly executing ones from new_threads
        inf_idx = next((i for i, t in enumerate(new_threads) if t.remaining != -1),
                       len(new_threads))
        ready_threads += new_threads[:inf_idx]
        new_threads = new_threads[inf_idx:]

        idx = 0
        count = 0
        for thread in new_threads:
            if thread.remaining == 0:
                finished_threads.append(thread)
                continue
            idx = bisect.bisect(remaining_list, thread.remaining, idx)
            ready_threads.insert(idx + count, thread)
            count += 1

    def schedule(self):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        See :meth:`Scheduler.schedule() <schedsi.scheduler.Scheduler.schedule>`.
        """
        while True:
            rcu_copy, _, _ = yield from self._start_schedule()
            idx = 0
            if not rcu_copy.data.ready_threads:
                idx = -1
            yield from self._schedule(idx, rcu_copy)
