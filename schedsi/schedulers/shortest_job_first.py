#!/usr/bin/env python3
"""Defines a shortest job first scheduler."""

import bisect
from schedsi.schedulers import first_come_first_serve


class SJF(first_come_first_serve.FCFS):
    """Shortest job first scheduler."""

    def _update_ready_chains(self, time, rcu_data):
        """See :meth:`FCFS._update_ready_chains`.

        To make the scheduling decision easier,
        the threads will be sorted by remaining time.
        """
        ready_chains = rcu_data.ready_chains
        finished_chains = rcu_data.finished_chains
        new_idx = len(ready_chains)
        super()._update_ready_chains(time, rcu_data)

        new_chains = ready_chains[new_idx:]
        del ready_chains[new_idx:]

        # we sort the list to make insertion easier
        new_chains = sorted(new_chains, key=lambda c: c.bottom.remaining or -1)

        # remaining_list should contain the remaining times of all non-infinitly threads
        inf_idx = next((i for i, c in enumerate(ready_chains) if c.bottom.remaining is None), None)
        remaining_list = list(c.bottom.remaining for c in ready_chains[:inf_idx])

        # filter out the infinitly executing ones from new_chains
        inf_idx = next((i for i, c in enumerate(new_chains) if c.bottom.remaining is not None),
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
