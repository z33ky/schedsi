#!/usr/bin/env python3
"""Sample/test for schedsi.

The test consists of a kernel using the round robin scheduler
to schedule two threads - one continuously executing,
one with periodic bursts.
"""

import datetime
import sys
from schedsi import textlog, module, round_robin, threads, world

def main():
    """Run the test"""
    kernel = module.Module("0", None, round_robin.RoundRobin)
    top_module = module.Module("0.0", kernel, round_robin.RoundRobin)

    kernel.add_threads([
        threads.Thread(kernel, 1, 0, 50),
        threads.PeriodicWorkThread(kernel, 2, 5, 50, 20, 5),
        threads.VCPUThread(kernel, 3, top_module)
    ])
    top_module.add_threads([
        threads.Thread(top_module, 1, 0, 25)
    ])

    cpu = world.Core(0, 10)
    log_file_name = sys.argv[1] if len(sys.argv) > 1 \
                                else datetime.datetime.now().isoformat() + ".log"
    log_file = textlog.TextLog(log_file_name, # pylint: disable=too-many-function-args
                               textlog.TextLogAlign(cpu=1, time=3, module=7, thread=1)) # pylint: disable=no-member

    the_world = world.World(cpu, kernel)
    while the_world.step(log_file) < 150:
        pass

if __name__ == '__main__':
    main()
