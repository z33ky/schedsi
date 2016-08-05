#!/usr/bin/env python3
"""Sample/test for schedsi.

The test consists of a kernel using the round robin scheduler
to schedule two threads - one continuously executing,
one with periodic bursts.
"""

import datetime
import io
import sys
from schedsi import binarylog, cpu, module, round_robin, textlog, threads, world

def main():
    """Run the test"""

    #Create a hierarchy of a kernel module and a child module.
    kernel = module.Module("0", None, round_robin.RoundRobin)
    top_module = module.Module("0.0", kernel, round_robin.RoundRobin)

    #Add two work threads to the kernel and one scheduler thread to run the child.
    #pylint: disable=duplicate-code
    kernel.add_threads([
        threads.Thread(kernel, 1, 0, 50),
        threads.PeriodicWorkThread(kernel, 2, 5, 50, 20, 5),
        threads.VCPUThread(kernel, 3, top_module)
    ])
    #Add one work thread to the child.
    top_module.add_threads([
        threads.Thread(top_module, 1, 0, 25)
    ])

    #Create the logger.
    now = datetime.datetime.now().isoformat()
    log_file_name = sys.argv[1] if len(sys.argv) > 1 else now + ".msgpack"
    log_file = open(log_file_name, 'xb') if log_file_name != "-" else io.BytesIO()
    binary_log = binarylog.BinaryLog(log_file)

    #Create and run the world.
    the_world = world.World(cpu.Core(0, 10), kernel, binary_log)
    while the_world.step() < 150:
        pass

    #Create a human-readable log.
    text_log_file_name = sys.argv[2] if len(sys.argv) > 2 else now + ".log"
    text_log_file = open(text_log_file_name, 'x') if text_log_file_name != '-' else sys.stdout
    text_log = textlog.TextLog(text_log_file,
                               textlog.TextLogAlign(cpu=1, time=3, module=7, thread=1))
    log_input = open(log_file_name, 'rb') if not isinstance(log_file, io.BytesIO) \
                                          else io.BytesIO(log_file.getvalue())
    binarylog.replay(log_input, text_log)

if __name__ == '__main__':
    main()
