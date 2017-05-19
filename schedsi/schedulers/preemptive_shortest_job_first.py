#!/usr/bin/env python3
"""Defines a preemptible shortest job first scheduler."""

from schedsi.cpu.request import Request as CPURequest
from . import shortest_job_first


class PSJF(shortest_job_first.SJF):
    """Preemptive shortest job first scheduler.

    Only sets up preemption on reschedule.
    Threads that are added will be regarded on the next reschedule, but never cause preemption.
    The local timer strategy may suspend and resume scheduling chains without scheduler
    invocations, which can result in delayed preemption.
    """

    def _sched_loop(self, rcu_copy, last_chain_queue, last_chain_idx):  # pylint: disable=no-self-use
        """See :meth:`FCFS._sched_loop`."""
        idx, time_slice = yield from super()._sched_loop(rcu_copy, last_chain_queue, last_chain_idx)
        if idx != -1:
            assert idx == 0
            waiting_chains = rcu_copy.data.waiting_chains
            if waiting_chains:
                threads = (c.bottom for c in waiting_chains)
                next_thread = next(threads)
                for thread in threads:
                    if thread.ready_time < next_thread.ready_time or (
                            thread.ready_time == next_thread.ready_time
                            and thread.remaining < next_thread.remaining):
                        next_thread = thread
                current_remaining = rcu_copy.data.ready_chains[0].bottom.remaining
                if next_thread.remaining is not None and (
                        current_remaining is None or next_thread.remaining < current_remaining):
                    current_time = yield CPURequest.current_time()
                    time_slice = next_thread.ready_time - current_time
                    assert time_slice > 0
        return idx, time_slice
