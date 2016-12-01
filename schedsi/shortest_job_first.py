#!/usr/bin/env python3
"""Defines a shortest job first scheduler."""

import bisect
from schedsi import scheduler

class SJF(scheduler.Scheduler):
    """Shortest job first scheduler."""

    def __init__(self, module):
        """Create a :class:`SJF` scheduler."""
        super().__init__(module)

    def _update_ready_chains(self, time, rcu_data):
        """See :meth:`Scheduler._update_ready_chains`.

        To make the scheduling decision easier,
        the threads will be sorted by remaining time.
        """
        ready_chains = rcu_data.ready_chains
        finished_chains = rcu_data.finished_chains
        new_idx = len(ready_chains)
        super()._update_ready_chains(time, rcu_data)
        assert rcu_data.last_idx == -1

        new_chains = ready_chains[new_idx:]
        del ready_chains[new_idx:]

        #we sort the list to make insertion easier
        new_chains = sorted(new_chains, key=lambda c: c.bottom.remaining)

        #remaining_list should contain the remaining times of all non-infinitly threads
        inf_idx = next((i for i, c in enumerate(ready_chains) if c.bottom.remaining == -1), None)
        remaining_list = list(c.bottom.remaining for c in ready_chains[:inf_idx])

        #filter out the infinitly executing ones from new_chains
        inf_idx = next((i for i, c in enumerate(new_chains) if c.bottom.remaining != -1),
                       len(new_chains))
        ready_chains += new_chains[:inf_idx]
        new_chains = new_chains[inf_idx:]

        idx = 0
        count = 0
        for ctx in new_chains:
            if ctx.bottom.is_finished():
                finished_chains.append(ctx)
                continue
            idx = bisect.bisect(remaining_list, ctx.bottom.remaining, idx)
            ready_chains.insert(idx + count, ctx)
            count += 1

    def _sched_loop(self, rcu_copy, _last_chain_queue, _last_chain_idx):
        """Schedule the next :class:`~schedsi.threads.Thread`.

        See :meth:`~schedsi.scheduler.Scheduler._sched_loop`.
        """
        idx = 0
        if not rcu_copy.data.ready_chains:
            idx = -1
        return idx
        #needs to be a coroutine
        yield # pylint: disable=unreachable
