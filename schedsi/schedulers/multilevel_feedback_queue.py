#!/usr/bin/env python3
"""Defines a multi-level feedback queue scheduler."""

import itertools
from schedsi.schedulers import scheduler
from schedsi.cpu.request import Request as CPURequest


class MLFQData(scheduler.SchedulerData):  # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`MLFQ` scheduler."""

    def __init__(self, levels, priority_boost_time):
        """Create a :class:`MLFQData`."""
        super().__init__()

        # note: queues with low index are high priority and vice versa
        self.ready_queues = []

        self.waiting_queues = []

        # TODO: rr_index per ready_queue
        for _ in range(0, levels):
            self.ready_queues.append([])
            self.waiting_queues.append([])

        assert not self.ready_chains
        self.ready_chains = self.ready_queues[0]
        # we keep waiting_chains its dedicated list and empty it on demand
        # assert not self.waiting_chains
        # self.waiting_chains = self.waiting_queues[0]

        self.prio_boost_time = priority_boost_time
        self.last_prio_boost = None
        self.last_finish_time = None


class MLFQ(scheduler.Scheduler):
    """Multi-level feedback queue scheduler.

    If `level_time_slices` is specified for :meth:`__init__`, this scheduler
    will use time-slices and can thus not be used outside the kernel with the
    single timer scheduling strategy.
    Use the :class:`~schedulers.addons.Penalizer` or the
    :class:`~schedulers.addons.TimeSliceFixer` for this case.
    """

    def __init__(self, module, *, level_time_slices=None, priority_boost_time, **kwargs):
        """Create a class:`MLFQ`."""
        if level_time_slices is None:
            levels = 8
        else:
            levels = len(level_time_slices)
        assert levels > 0

        if priority_boost_time is not None:
            # priority boost has no effect with 1 queue
            assert levels != 1
            assert priority_boost_time >= 0

        super().__init__(module, MLFQData(levels, priority_boost_time), **kwargs)

        self.level_time_slices = level_time_slices
        if level_time_slices is None:
            self.level_time_slices = (self.time_slice,) * levels
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

    def all_threads(self):
        """See :meth:`Scheduler.all_threads`."""
        rcu_data = self._rcu.read()
        return (ctx.bottom for queue in itertools.chain(rcu_data.ready_queues,
                                                        rcu_data.waiting_queues,
                                                        (rcu_data.finished_chains,))
                for ctx in queue)

    @classmethod
    def _update_ready_chains(cls, time, rcu_data):
        """See :meth:`Scheduler._update_ready_chains`.

        This function updates multiple queues.
        Switching to the highest priority queue is handled in
        :meth:`_start_schedule`.
        """
        for (ready, waiting) in zip(rcu_data.ready_queues, rcu_data.waiting_queues):
            cls._update_ready_chain_queues(time, ready, waiting)

        # do a sanity check while we're here
        assert all((not t.bottom.is_finished() for t in ready)
                   for ready in rcu_data.ready_queues)
        assert all(t.bottom.is_finished() for t in rcu_data.finished_chains)

    def get_next_waiting(self, rcu_data):
        """See :meth:`Scheduler.get_next_waiting`."""
        next_waiting = None
        assert not rcu_data.waiting_chains
        waiting_queue = rcu_data.waiting_chains
        for queue in rcu_data.waiting_queues:
            rcu_data.waiting_chains = queue
            candidate = super().get_next_waiting(rcu_data)
            if candidate is not None:
                if next_waiting is None or \
                   next_waiting.bottom.ready_time > candidate.bottom.ready_time:
                    next_waiting = candidate
        rcu_data.waiting_chains = waiting_queue
        return next_waiting

    def _start_schedule(self, prev_run_time):  # pylint: disable=method-hidden
        """See :meth:`Scheduler._start_schedule`.

        Lower priority of last thread if it outran its time-slice.
        Boost priorities if it's time.
        """
        rcu_copy, last_queue, last_idx = yield from super()._start_schedule(prev_run_time)
        rcu_data = rcu_copy.data

        prev_still_ready = last_queue is rcu_data.ready_chains
        prev_has_run = prev_run_time is not None and prev_run_time > 0
        prev_level = next(i for i, v in enumerate(rcu_data.ready_queues)
                          if v is rcu_data.ready_chains)

        if prev_has_run:
            # important: == vs is; empty arrays will compare equal with ==
            current_time = (yield CPURequest.current_time())

            if self._priority_boost(rcu_data, prev_level, current_time) \
                and prev_still_ready:
                last_queue = rcu_data.ready_queues[0]

        if prev_still_ready:
            # rotate queue for round robin
            last_queue.append(last_queue.pop(last_idx))
            last_idx = len(last_queue) - 1

        # switch to highest priority queue
        rcu_data.ready_chains = next((x for x in rcu_data.ready_queues if x),
                                     rcu_data.ready_queues[0])

        if prev_has_run and not last_queue[-1].bottom.is_finished():
            # and (rcu_data.last_prio_boost is None or rcu_data.last_prio_boost != current_time) ?
            last_queue = self._priority_reduction(rcu_data, last_queue,
                                                  prev_still_ready, prev_level, prev_run_time)
        if rcu_data.waiting_chains:
            assert last_queue is rcu_data.waiting_chains
            last_queue = rcu_data.waiting_queues[prev_level]
            last_queue.append(rcu_data.waiting_chains.pop())
            assert not rcu_data.waiting_chains

        return rcu_copy, last_queue, last_idx

    def _get_last_chain(self, _rcu_data, last_chain_queue, _last_chain_idx):
        """See :meth:`Scheduler._get_last_chain`."""
        # the last chain is always at the end
        return last_chain_queue[-1] if last_chain_queue else None

    # this may get overwritten by _no_priority_boost
    def _priority_boost(self, rcu_data, prev_level, current_time):  # pylint: disable=method-hidden
        """Put all threads in highest priority if :attr:`prio_boost_time` elapsed.

        This is to avoid starvation.

        This function should be run before selecting a new :attr:`ready_chains`.

        Apart from `rcu_data`, this function takes the level the previously executed
        thread was at and the current time.

        Returns whether priority was boosted.
        """
        assert self.prio_boost_time is not None
        if rcu_data.last_prio_boost is None:
            rcu_data.last_prio_boost = current_time
        delta = current_time - rcu_data.last_prio_boost
        if rcu_data.prio_boost_time <= delta:
            boosted = True

            for old_queues in (rcu_data.ready_queues, rcu_data.waiting_queues):
                # the order only really matters for ready_queues
                new_queue = []
                for _ in map(new_queue.extend, old_queues[prev_level:] + old_queues[:prev_level]):
                    pass
                old_queues[0] = new_queue
                for queue in old_queues[1:]:
                    queue.clear()

            rcu_data.prio_boost_time = self.prio_boost_time - (delta - rcu_data.prio_boost_time)
        else:
            boosted = False
            rcu_data.prio_boost_time -= delta
        rcu_data.last_prio_boost = current_time

        return boosted

    def _no_priority_boost(self, _rcu_data, _prev_level, _current_time):  # pylint: disable=no-self-use
        """Overwrite :meth:`_priority_boost` if :attr:`prio_boost_time` is `None`.

        A no-op.

        See :meth:`_priority_boost`.
        """
        assert self.prio_boost_time is None
        return False

    def _priority_reduction(self, rcu_data, last_queue,  # pylint: disable=no-self-use
                            prev_still_ready, prev_level, prev_run_time):
        """Lower last thread's priority if it outran its time-slice.

        This represents the heuristic of the MLFQ scheduler.

        This function should be run after selecting a new :attr:`ready_chains`.

        Apart from `rcu_data`, this function takes the `last_queue` as returned by
        :meth:`_start_schedule`, a `bool` indicating if the previously executed thread
        is still ready, the level the previously executed thread was at and its previous run-time.

        Since this changes the queues around, the updated `last_queue` is returned.
        """
        allowed_run_time = self.level_time_slices[prev_level]
        if allowed_run_time is None:
            allowed_run_time = prev_run_time

        next_queue_idx = prev_level + 1

        if rcu_data.last_finish_time is None \
           or prev_run_time < allowed_run_time \
           or prev_run_time == allowed_run_time and last_queue[-1].bottom.ready_time != rcu_data.last_finish_time \
           or next_queue_idx == len(self.level_time_slices):
            return last_queue

        next_chain_queue = None
        if prev_still_ready:
            next_chain_queue = rcu_data.ready_queues[next_queue_idx]
        elif rcu_data.waiting_chains:
            assert last_queue is rcu_data.waiting_chains
            next_chain_queue = rcu_data.waiting_queues[next_queue_idx]
        else:
            assert last_queue in (None, rcu_data.finished_chains)

        if next_chain_queue is not None:
            next_chain_queue.append(last_queue.pop())
            last_queue = next_chain_queue

            assert not rcu_data.waiting_chains

            if not rcu_data.ready_chains:
                if prev_still_ready:
                    rcu_data.ready_chains = last_queue
                else:
                    candidates = rcu_data.ready_queues[next_queue_idx:]
                    rcu_data.ready_chains = next((x for x in candidates if x),
                                                 rcu_data.ready_queues[0])

        return last_queue

    def _sched_loop(self, rcu_copy, _last_chain_queue, _last_chain_idx):
        """Schedule the next :class:`~schedsi.threads.Thread`.

        See :meth:`Scheduler._sched_loop() <schedsi.scheduler.Scheduler._sched_loop>`.
        """
        rcu_data = rcu_copy.data

        if not rcu_data.ready_chains:
            return -1, None

        # important: == vs is; empty arrays will compare equal with ==
        level = next(i for i, v in enumerate(rcu_data.ready_queues)
                     if v is rcu_data.ready_chains)

        time_slice = self.level_time_slices[level]
        rcu_data.last_finish_time = None
        if time_slice is not None:
            rcu_data.last_finish_time = (yield CPURequest.current_time()) + time_slice

        return 0, time_slice
