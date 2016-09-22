#!/usr/bin/env python3
"""Sample/test for schedsi.

The test consists of a kernel using the round robin scheduler
to schedule two threads - one continuously executing,
one with periodic bursts.
"""

import sys
from schedsi import binarylog, module, schedulers, threads, world

#Create a hierarchy of a kernel module and a child module.
#this is the same as tests/simple_hierarchy.py
#pylint: disable=duplicate-code
KERNEL = module.Module("0", None, schedulers.RoundRobin)
TOP_MODULE = module.Module("0.0", KERNEL, schedulers.RoundRobin)
BOTTOM_MODULE_A = module.Module("0.0.0", TOP_MODULE, schedulers.RoundRobin)
BOTTOM_MODULE_B = module.Module("0.0.1", TOP_MODULE, schedulers.SJF)

#Add two work threads to the KERNEL and one scheduler thread to run the child.
KERNEL.add_threads([
    threads.Thread(KERNEL, 1, units=50),
    threads.PeriodicWorkThread(KERNEL, 2, ready_time=5, units=50, period=20, burst=5),
    threads.VCPUThread(KERNEL, 3, child=TOP_MODULE)
])
#Add one work thread to the child and two scheduler threads for its children.
TOP_MODULE.add_threads([
    threads.Thread(TOP_MODULE, 1, units=25),
    threads.VCPUThread(TOP_MODULE, 2, child=BOTTOM_MODULE_A),
    threads.VCPUThread(TOP_MODULE, 3, child=BOTTOM_MODULE_B)
])
#Add work threads to the grandchildren.
BOTTOM_MODULE_A.add_threads([
    threads.Thread(BOTTOM_MODULE_A, 1, units=10),
    threads.Thread(BOTTOM_MODULE_A, 2, ready_time=50, units=25)
])
BOTTOM_MODULE_B.add_threads([
    threads.PeriodicWorkThread(BOTTOM_MODULE_B, 1, units=10, period=10, burst=2),
    threads.PeriodicWorkThread(BOTTOM_MODULE_B, 2, period=10, burst=2),
    threads.Thread(BOTTOM_MODULE_B, 3, ready_time=10, units=10)
])

def main():
    """Run the test."""

    #Create the logger.
    log_file_name = sys.argv[1] if len(sys.argv) > 1 else "-"
    log_to_file = log_file_name != "-"
    with open(log_file_name, 'xb') if log_to_file else sys.stdout.buffer as log_file:
        binary_log = binarylog.BinaryLog(log_file)

        #Create and run the world.
        the_world = world.World(1, 10, KERNEL, binary_log)
        while the_world.step() <= 400:
            pass

if __name__ == '__main__':
    main()
