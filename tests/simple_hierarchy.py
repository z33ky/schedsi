#!/usr/bin/env python3
"""Create a simple hierarchy.

It consists of a kernel with two threads (plus one scheduling thread)
and a child-module with one thread.

Scheduling is done via RoundRobin on both modules.
"""

from schedsi import module, round_robin, threads

KERNEL = module.Module("0", None, round_robin.RoundRobin)
TOP_MODULE = module.Module("0.0", KERNEL, round_robin.RoundRobin)

KERNEL.add_threads([
    threads.Thread(KERNEL, 1, 0, 50),
    threads.PeriodicWorkThread(KERNEL, 2, 5, 50, 20, 5),
    threads.VCPUThread(KERNEL, 3, TOP_MODULE)
])
TOP_MODULE.add_threads([
    threads.Thread(TOP_MODULE, 1, 0, 25)
])
