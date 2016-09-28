#!/usr/bin/env python3
"""Defines a multi-level feedback queue scheduler."""

from schedsi import scheduler

class MLFQData(scheduler.SchedulerData): # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`MLFQ` scheduler."""

    def __init__(self, levels):
        """Create a :class:`MLFQData`."""
        super().__init__()

        #note: queues with low index are high priority and vice versa
        self.ready_queues = []

        self.waiting_queues = []

        #TODO: rr_index per ready_queue
        for _ in range(0, levels):
            self.ready_queues.append([])
            self.waiting_queues.append([])

        assert not self.ready_threads
        self.ready_threads = self.ready_queues[0]
        #assert not self.waiting_threads
        #self.waiting_threads = self.waiting_queues[0]

class MLFQ(scheduler.Scheduler):
    """Multi-level feedback queue scheduler."""

    def __init__(self, module, *, levels=8):
        """Create a class:`MLFQ`."""
        assert levels > 0
        super().__init__(module, MLFQData(levels))

    def add_threads(self, new_threads, rcu_data=None):
        """Add threads to schedule.

        New threads are put in the highest priority queue.
        """
        super_add_threads = super().add_threads
        def appliance(data):
            waiting_tmp = data.waiting_threads
            data.waiting_threads = data.waiting_queues[0]
            super_add_threads(new_threads, data)
            data.waiting_threads = waiting_tmp
        if rcu_data is None:
            self._rcu.apply(appliance)
        else:
            appliance(rcu_data)

    def num_threads(self):
        return self._rcu.look(lambda d:
                              sum(len(x) for x in
                                  d.ready_queues + d.waiting_queues + [d.finished_threads]))

    @classmethod
    def _update_ready_threads(cls, time, rcu_data):
        """See :meth:`Scheduler._update_ready_threads`.

        This function updates multiple queues.
        Switching to the highest priority queue is handled in
        :meth:`schedule`.
        """
        for (ready, waiting) in zip(rcu_data.ready_queues, rcu_data.waiting_queues):
            cls._update_ready_thread_queues(time, ready, waiting)

        #do a sanity check while we're here
        assert all((t.remaining != 0 for t in ready) for ready in rcu_data.ready_queues)
        assert all(t.remaining == 0 for t in rcu_data.finished_threads)

    def _sched_loop(self, rcu_copy, last_thread_queue, last_thread_idx):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        See :meth:`Scheduler.schedule() <schedsi.scheduler.Scheduler._sched_loop>`.
        """
        rcu_data = rcu_copy.data

        #switch to highest priority queue
        prev_ready_queue = rcu_data.ready_threads
        rcu_data.ready_threads = next((x for x in rcu_data.ready_queues if x),
                                      rcu_data.ready_threads)
        #important: == vs is; empty arrays will compare equal with ==
        prev_ready_queue_idx = next(i for i, v in enumerate(rcu_data.ready_queues)
                                    if v is prev_ready_queue)

        if last_thread_queue is prev_ready_queue:
            #previous thread outran its time-slice
            next_idx = prev_ready_queue_idx + 1
            if next_idx != len(rcu_data.ready_queues):
                next_thread_queue = rcu_data.ready_queues[next_idx]
                next_thread_queue.append(prev_ready_queue.pop(last_thread_idx))
                if not rcu_data.ready_threads:
                    rcu_data.ready_threads = next_thread_queue
                    last_thread_idx = len(next_thread_queue) - 1
                last_thread_queue = next_thread_queue
        elif rcu_data.waiting_threads:
            assert last_thread_queue is rcu_data.waiting_threads
            last_thread_queue = rcu_data.waiting_queues[prev_ready_queue_idx]
            last_thread_queue.append(rcu_data.waiting_threads.pop())
            assert not rcu_data.waiting_threads
        else:
            assert last_thread_queue is None or last_thread_queue is rcu_data.finished_threads


        #do a round robin
        num_threads = len(rcu_data.ready_threads)

        idx = num_threads
        if last_thread_queue is rcu_data.ready_threads:
            idx = last_thread_idx + 1
        elif not last_thread_queue is None:
            idx = last_thread_idx
        if idx == num_threads:
            idx = 0
            if num_threads == 0:
                idx = -1

        return idx
        #needs to be a coroutine
        yield # pylint: disable=unreachable
