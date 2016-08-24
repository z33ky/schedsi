#!/usr/bin/env python3
"""Sample/test for schedsi.

The test consists of a kernel using the round robin scheduler
to schedule two threads - one continuously executing,
one with periodic bursts.
"""

import datetime
import io
import sys
from schedsi import binarylog, module, round_robin, textlog, threads, world

def main():
    """Run the test"""

    #Create a hierarchy of a kernel module and a child module.
    kernel = module.Module("0", None, round_robin.RoundRobin)
    top_module = module.Module("0.0", kernel, round_robin.RoundRobin)

    #Add two work threads to the kernel and one scheduler thread to run the child.
    #this is the same as tests/simple_hierarchy.py
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
    buffer_log = log_file_name == "-"
    with io.BytesIO() if buffer_log else open(log_file_name, 'xb') as log_file:
        binary_log = binarylog.BinaryLog(log_file)

        #Create and run the world.
        the_world = world.World(1, 10, kernel, binary_log)
        while the_world.step() < 150:
            pass
        log_file.flush()

        #Create a human-readable log.
        text_log_file_name = sys.argv[2] if len(sys.argv) > 2 else now + ".log"
        stdout_log = text_log_file_name == '-'
        with sys.stdout if stdout_log else open(text_log_file_name, 'x') as text_log_file:
            text_log = textlog.TextLog(text_log_file,
                                       textlog.TextLogAlign(cpu=1, time=3, module=7, thread=1))
            log_input = io.BytesIO(log_file.getvalue()) if buffer_log else open(log_file_name, 'rb')
            binarylog.replay(log_input, text_log)

if __name__ == '__main__':
    main()
