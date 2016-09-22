#!/usr/bin/env python3
"""Defines the base class for schedulers."""

from schedsi import rcu

class SchedulerData: # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`Scheduler`.

    Mutable data for the scheduler needs to be updated atomically.
    To enable RCU this is kept in one class.
    """
    def __init__(self):
        """Create a :class:`SchedulerRCU`."""
        self.ready_threads = []
        self.waiting_threads = []
        self.finished_threads = []
        self.last_idx = -1

class Scheduler:
    """Scheduler.

    Has a :obj:`list` of :class:`Threads <schedsi.threads.Thread>`.
    """

    def __init__(self, module, rcu_storage=None):
        """Create a :class:`Scheduler`.

        Optionally takes a `rcu_storage` for which to create the :attr:`_rcu` for.
        It should be a subclass of :class:`SchedulerData`.
        """
        if rcu_storage is None:
            rcu_storage = SchedulerData()
        self._rcu = rcu.RCU(rcu_storage)
        self.module = module

    def num_threads(self):
        return self._rcu.look(lambda d:
                              sum(len(x) for x in
                                  [d.ready_threads, d.waiting_threads, d.finished_threads]))

    def add_threads(self, new_threads):
        """Add threads to schedule."""
        def appliance(data):
            """Append new threads to the waiting and finished queue."""
            data.waiting_threads += (n for n in new_threads if n.remaining != 0)
            data.finished_threads += (n for n in new_threads if n.remaining == 0)
        self._rcu.apply(appliance)

    def _update_ready_threads(self, time, rcu_data):
        """Moves threads becoming ready to the ready threads list."""
        rcu_data.ready_threads += (r for r in rcu_data.waiting_threads if r.ready_time <= time)
        rcu_data.waiting_threads = [r for r in rcu_data.waiting_threads if r.ready_time > time]

        #do a sanity check while we're here
        assert not (0, -1) in ((t.remaining, t.ready_time) for t in rcu_data.ready_threads)
        assert all(t.remaining == 0 for t in rcu_data.finished_threads)

    def _start_schedule(self):
        """Prepare making a scheduling decision.

        Moves ready threads to the ready queue
        and finished ones to the finished queue.

        Returns a tuple (RCUCopy of :attr:`rcu`, flag whether
        previously scheduled thread has finished).
        The latter tuple element can be of interest for
        scheduling algorithms that store an index to the thread list.

        Yields the amount of time it wants to execute. None for no-op.
        This is a subset of :meth:`schedule`.
        Consumes the current time.
        """
        current_time = yield
        while True:
            rcu_copy = self._rcu.copy()
            rcu_data = rcu_copy.data

            #check if the last scheduled thread is done now
            #move to a different queue is necessary
            removed = False
            if rcu_data.last_idx != -1:
                last_thread = rcu_data.ready_threads[rcu_data.last_idx]
                dest = None

                if last_thread.remaining == 0:
                    dest = rcu_data.finished_threads
                elif last_thread.ready_time > current_time:
                    dest = rcu_data.waiting_threads
                else:
                    assert last_thread.ready_time != -1

                if not dest is None:
                    removed = True
                    dest.append(rcu_data.ready_threads.pop(rcu_data.last_idx))
                    rcu_data.last_idx = -1
                    if not self._rcu.update(rcu_copy):
                        #current_time = yield 1
                        continue

            self._update_ready_threads(current_time, rcu_data)

            return rcu_copy, removed

    def _schedule(self, idx, rcu_copy):
        """Schedule the thread at `idx`.

        Returns a flag indicating if the thread was successfully scheduled.
        Yields the thread to execute.
        """
        rcu_copy.data.last_idx = idx
        if not self._rcu.update(rcu_copy):
            return False

        yield rcu_copy.data.ready_threads[idx]
        return True

    def schedule(self):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        This :class:`Scheduler` is a base class.
        This function will only deal with a single :class:`Thread <schedsi.threads.Thread>`.
        If more are present, a :exc:`RuntimeError` is raised.

        Yields the amount of time it wants to execute,
        0 to indicate the desire to yield, or a thread to switch to.
        None for no-op.
        Consumes the current time.
        """
        while True:
            rcu_copy, _ = yield from self._start_schedule()
            num_threads = len(rcu_copy.data.ready_threads)
            if num_threads == 0:
                yield 0
                return
            if num_threads != 1:
                raise RuntimeError('Scheduler cannot make scheduling decision.')
            yield from self._schedule(0, rcu_copy)
