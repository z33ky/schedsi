#!/usr/bin/env python3
"""Defines a shortest job first scheduler."""

import bisect
from schedsi import scheduler

class SJF(scheduler.Scheduler):
    """Shortest job first scheduler."""

    def __init__(self, module):
        """Create a :class:`SJF` scheduler."""
        super().__init__(module)

    def add_threads(self, new_threads):
        """Add threads to schedule.

        To make the scheduling decision easier,
        the threads will be sorted by remaining time."""
        #we sort the list to make insertion easier
        new_threads = sorted(new_threads, key=lambda t: t.remaining)

        #remaining_list should contain the remaining times of all non-infinitly threads
        #so for inf_idx we could the number of -1 from the back
        inf_idx = next((i for i, t in enumerate(reversed(self._threads)) if t.remaining != -1),
                       len(self._threads))
        remaining_list = list(t.remaining for t in self._threads[0:-inf_idx])

        #filter out the infinitly executing ones from new_threads
        inf_idx = next((i for i, t in enumerate(new_threads) if t.remaining != -1),
                       len(new_threads))
        self._threads += new_threads[0:inf_idx]
        new_threads = new_threads[inf_idx:]

        idx = 0
        count = 0
        for thread in new_threads:
            if thread.remaining == 0:
                self._finished_threads.append(thread)
                continue
            idx = bisect.bisect(remaining_list, thread.remaining, idx)
            self._threads.insert(idx + count, thread)
            count += 1

    def schedule(self, cpu):
        """Run the next :class:`Thread <schedsi.threads.Thread>`.

        See :meth:`Scheduler.schedule() <schedsi.scheduler.Scheduler.schedule>`.
        """
        thread, idx = next(self._get_ready_threads(cpu), (None, None))
        run_time, removed = self._run_thread(thread, cpu)

        #resort
        #this is required if we have unready threads in front of the queue
        if not removed and thread:
            for prev_idx, prev_thread in enumerate(self._threads[:idx]):
                if prev_thread.remaining > thread.remaining:
                    self._threads.insert(prev_idx, self._threads.pop(idx))
                    break

        if cpu.status.pending_interrupt or run_time == 0:
            return 0

        return run_time + self.schedule(cpu)
