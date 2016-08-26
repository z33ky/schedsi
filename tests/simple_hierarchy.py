#!/usr/bin/env python3
"""Create a simple hierarchy.

It consists of
    * a kernel with two threads (plus one VCPU thread)
    * a child-module with one thread (plus two VCPU threads)
    * two grandchildren with a total of five threads

Scheduling is done via RoundRobin on both modules.
"""

from schedsi import module, round_robin, threads

KERNEL = module.Module("0", None, round_robin.RoundRobin)
TOP_MODULE = module.Module("0.0", KERNEL, round_robin.RoundRobin)
BOTTOM_MODULE_A = module.Module("0.0.0", TOP_MODULE, round_robin.RoundRobin)
BOTTOM_MODULE_B = module.Module("0.0.1", TOP_MODULE, round_robin.RoundRobin)

#Add two work threads to the KERNEL and one scheduler thread to run the child.
KERNEL.add_threads([
    threads.Thread(KERNEL, 1, 0, 50),
    threads.PeriodicWorkThread(KERNEL, 2, 5, 50, 20, 5),
    threads.VCPUThread(KERNEL, 3, TOP_MODULE)
])
#Add one work thread to the child and two scheduler threads for its children.
TOP_MODULE.add_threads([
    threads.Thread(TOP_MODULE, 1, 0, 25),
    threads.VCPUThread(TOP_MODULE, 2, BOTTOM_MODULE_A),
    threads.VCPUThread(TOP_MODULE, 3, BOTTOM_MODULE_B)
])
#Add work threads to the grandchildren.
BOTTOM_MODULE_A.add_threads([
    threads.Thread(BOTTOM_MODULE_A, 1, 0, 10),
    threads.Thread(BOTTOM_MODULE_A, 2, 50, 25)
])
BOTTOM_MODULE_B.add_threads([
    threads.PeriodicWorkThread(BOTTOM_MODULE_B, 1, 0, 10, 10, 2),
    threads.PeriodicWorkThread(BOTTOM_MODULE_B, 2, 0, -1, 10, 2),
    threads.Thread(BOTTOM_MODULE_B, 3, 10, 10)
])
