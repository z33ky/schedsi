#!/usr/bin/env python3
"""Sample/test for schedsi.

The test consists of a kernel using the round robin scheduler
to schedule two threads - one continuously executing,
one with periodic bursts.
"""

import datetime
from schedsi import textlog, module, round_robin, threads, world

def main():
    """Run the test"""
    kernel = module.Module("0", None, round_robin)
    kernel.threads = [
        threads.Thread(kernel, 1, 0, 50),
        threads.PeriodicWorkThread(kernel, 2, 5, 50, 20, 5)
    ]

    cpu = world.Core(0, 10)
    log_file = textlog.TextLog(datetime.datetime.now().isoformat() + ".log", # pylint: disable=too-many-function-args
                               textlog.TextLogAlign(cpu=1, time=3, module=7, thread=1)) # pylint: disable=no-member

    the_world = world.World(cpu, kernel)
    while the_world.step(log_file) < 100:
        pass

if __name__ == "__main__":
    main()
