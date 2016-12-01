#!/usr/bin/env python3
"""Defines a multi-level feedback queue scheduler.

This scheduler does not prevent gaming the scheduler by
almost, but not completely, running for a time-slice.
Such a thread will not get a priority reduction.
"""

from schedsi import cpurequest, scheduler

class MLFQData(scheduler.SchedulerData): # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`MLFQ` scheduler."""

    def __init__(self, levels, priority_boost_time):
        """Create a :class:`MLFQData`."""
        super().__init__()

        #note: queues with low index are high priority and vice versa
        self.ready_queues = []

        self.waiting_queues = []

        #TODO: rr_index per ready_queue
        for _ in range(0, levels):
            self.ready_queues.append([])
            self.waiting_queues.append([])

        assert not self.ready_chains
        self.ready_chains = self.ready_queues[0]
        #assert not self.waiting_chains
        #self.waiting_chains = self.waiting_queues[0]

        self.prio_boost_time = priority_boost_time
        self.last_prio_boost = None

        self.previous_ready_queue = None

class MLFQ(scheduler.Scheduler):
    """Multi-level feedback queue scheduler."""

    def __init__(self, module, *, levels=8, priority_boost_time):
        """Create a class:`MLFQ`."""
        assert levels > 0
        if not priority_boost_time is None:
            #priority boost has no effect with 1 queue
            assert levels != 1
            assert priority_boost_time >= 0
        super().__init__(module, MLFQData(levels, priority_boost_time))
        self.prio_boost_time = priority_boost_time
        if priority_boost_time is None:
            self._priority_boost = self._no_priority_boost

    def add_thread(self, thread, rcu_data=None):
        """Add threads to schedule.

        New threads are put in the highest priority queue.
        """
        super_add_thread = super().add_thread
        def appliance(data):
            """Append new threads to the waiting and finished queue."""
            waiting_tmp = data.waiting_chains
            data.waiting_chains = data.waiting_queues[0]
            super_add_thread(thread, data)
            data.waiting_chains = waiting_tmp
        if rcu_data is None:
            self._rcu.apply(appliance)
        else:
            appliance(rcu_data)

    def num_threads(self):
        """Return total number of threads.

        See :meth:`Thread.num_threads`.
        """
        return self._rcu.look(lambda d:
                              sum(len(x) for x in
                                  d.ready_queues + d.waiting_queues + [d.finished_chains]))

    @classmethod
    def _update_ready_chains(cls, time, rcu_data):
        """See :meth:`Scheduler._update_ready_chains`.

        This function updates multiple queues.
        Switching to the highest priority queue is handled in
        :meth:`_start_schedule`.
        """
        for (ready, waiting) in zip(rcu_data.ready_queues, rcu_data.waiting_queues):
            cls._update_ready_chain_queues(time, ready, waiting)

        #do a sanity check while we're here
        assert all((not t.bottom.is_finished() for t in ready)
                   for ready in rcu_data.ready_queues)
        assert all(t.bottom.is_finished() for t in rcu_data.finished_chains)

    def _start_schedule(self, prev_run_time): # pylint: disable=method-hidden
        """See :meth:`Scheduler._start_schedule`.

        Lower priority of last thread if it outran its time-slice.
        Boost priorities if it's time.
        """
        rcu_copy, last_queue, last_idx = yield from super()._start_schedule(prev_run_time)
        rcu_data = rcu_copy.data

        prev_has_run = not prev_run_time is None and prev_run_time > 0
        #important: == vs is; empty arrays will compare equal with ==
        prev_ready_queue_idx = next(i for i, v in enumerate(rcu_data.ready_queues)
                                    if v is rcu_data.ready_chains)

        if prev_has_run:
            current_time = (yield cpurequest.Request.current_time())
            (last_queue,
             last_idx,
             prev_ready_queue_idx) = self._priority_boost(rcu_data, last_queue, last_idx,
                                                          prev_ready_queue_idx, current_time)

        rcu_data.previous_ready_queue = rcu_data.ready_chains

        #switch to highest priority queue
        prev_ready_queue = rcu_data.ready_chains
        rcu_data.ready_chains = next((x for x in rcu_data.ready_queues if x),
                                     rcu_data.ready_chains)

        if prev_has_run:
            #and (rcu_data.last_prio_boost is None or rcu_data.last_prio_boost != current_time) ?
            last_queue, last_idx = self._priority_reduction(rcu_data,
                                                            last_queue, last_idx,
                                                            prev_ready_queue, prev_ready_queue_idx)
        elif last_queue is rcu_data.waiting_chains:
            assert rcu_data.waiting_chains
            last_queue = rcu_data.waiting_queues[prev_ready_queue_idx]
            last_queue.append(rcu_data.waiting_chains.pop())
            assert not rcu_data.waiting_chains

        return rcu_copy, last_queue, last_idx

    def _get_last_chain(self, rcu_data, last_chain_queue, last_chain_idx):
        """See :meth:`Scheduler._get_last_chain`."""
        ready_chains = rcu_data.ready_chains
        rcu_data.ready_chains = rcu_data.previous_ready_queue
        chain = super()._get_last_chain(rcu_data, last_chain_queue, last_chain_idx)
        rcu_data.ready_chains = ready_chains
        return chain

    # this may get overwritten by _no_priority_boost
    def _priority_boost(self, rcu_data, last_queue, last_idx, prev_ready_queue_idx, current_time): # pylint: disable=method-hidden
        """Put all threads in highest priority if :attr:`prio_boost_time` elapsed.

        This is to avoid starvation.

        This function should be run before selecting a new :attr:`ready_chains`.

        This function takes the return values of :meth:`_start_schedule`,
        the index of :attr:`ready_chains` in :attr:`ready_queues` and the current time.

        Since this changes the queues around, the updated values for
        `last_queue`, `last_idx` and `prev_ready_queue_idx` are returned.

        `prev_ready_queue_idx` could be obtained within this function
        and the new value from outside by finding the index of :attr:`ready_chains`
        in :attr:`ready_queues`, but it is passed in and out as an
        optimization.
        """
        assert not self.prio_boost_time is None
        if rcu_data.last_prio_boost is None:
            rcu_data.last_prio_boost = current_time
        delta = current_time - rcu_data.last_prio_boost
        if rcu_data.prio_boost_time <= delta:
            if last_queue is rcu_data.ready_chains:
                last_idx += sum(len(queue) for queue in
                                rcu_data.ready_queues[0:prev_ready_queue_idx])
                last_queue = rcu_data.ready_queues[0]
            rcu_data.ready_chains = rcu_data.ready_queues[0]
            prev_ready_queue_idx = 0
            for queue in rcu_data.ready_queues[1:]:
                if not queue is rcu_data.ready_chains:
                    rcu_data.ready_chains.extend(queue)
                    del queue[:]
            rcu_data.prio_boost_time = self.prio_boost_time - (delta - rcu_data.prio_boost_time)
        else:
            rcu_data.prio_boost_time -= delta
        rcu_data.last_prio_boost = current_time

        return last_queue, last_idx, prev_ready_queue_idx

    def _no_priority_boost(self, _rcu_data, last_queue, last_idx, prev_ready_queue_idx, # pylint: disable=no-self-use
                           _current_time):
        """This overwrites :meth:`_priority_boost` if :attr:`prio_boost_time` is `None`.

        A no-op.

        See :meth:`_priority_boost`."""
        return last_queue, last_idx, prev_ready_queue_idx

    def _priority_reduction(self, rcu_data, last_queue, last_idx, # pylint: disable=no-self-use
                            prev_ready_queue, prev_ready_queue_idx):
        """Lower last thread's priority if it outran its time-slice.

        This represents the heuristic of the MLFQ scheduler.

        This function should be run after selecting a new :attr:`ready_chains`.

        This function takes the return values of :meth:`_start_schedule`,
        the previous :attr:`ready_chains` and the index of that in :attr:`ready_queues`.

        Since this changes the queues around, the updated values for
        `last_queue` and `last_idx` are returned.

        `prev_ready_queue_idx` could be obtained within this function
        by finding the index of `prev_ready_queue` in :attr:`ready_queues`,
        but it is passed in as an optimization.
        """
        if last_queue is prev_ready_queue:
            #previous thread outran its time-slice
            next_idx = prev_ready_queue_idx + 1
            if next_idx != len(rcu_data.ready_queues):
                next_chain_queue = rcu_data.ready_queues[next_idx]
                next_chain_queue.append(prev_ready_queue.pop(last_idx))
                if not rcu_data.ready_chains:
                    rcu_data.ready_chains = next_chain_queue
                    last_idx = len(next_chain_queue) - 1
                last_queue = next_chain_queue
        elif rcu_data.waiting_chains:
            assert last_queue is rcu_data.waiting_chains
            last_queue = rcu_data.waiting_queues[prev_ready_queue_idx]
            last_queue.append(rcu_data.waiting_chains.pop())
            assert not rcu_data.waiting_chains
        else:
            assert last_queue is None or last_queue is rcu_data.finished_chains

        return last_queue, last_idx

    def _sched_loop(self, rcu_copy, last_chain_queue, last_chain_idx):
        """Schedule the next :class:`~schedsi.threads.Thread`.

        See :meth:`Scheduler._sched_loop() <schedsi.scheduler.Scheduler._sched_loop>`.
        """
        rcu_data = rcu_copy.data

        #do a round robin
        num_chains = len(rcu_data.ready_chains)

        idx = num_chains
        if last_chain_queue is rcu_data.ready_chains:
            idx = last_chain_idx + 1
        elif not last_chain_queue is None:
            idx = last_chain_idx
        if idx == num_chains:
            idx = 0
            if num_chains == 0:
                idx = -1

        return idx
        #needs to be a coroutine
        yield # pylint: disable=unreachable
