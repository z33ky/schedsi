#!/usr/bin/env python3
"""Sample/test for CFS."""

# pylint: disable=duplicate-code
import sys
from schedsi import schedulers, threads, world
from schedsi.log import binarylog
from schedsi.util import hierarchy_builder

KERNEL = hierarchy_builder.ModuleBuilder(scheduler=schedulers.CFS.builder(default_shares=400,
                                                                          min_period=30,
                                                                          min_slice=6,
                                                                          time_slice=None))

KERNEL.add_thread(threads.Thread, {'shares': 1000}) \
      .add_thread(threads.PeriodicWorkThread, {'shares': 250},
                  ready_time=5, units=256, period=160, burst=4) \
      .add_thread(threads.PeriodicWorkThread, {'shares': 250},
                  ready_time=25, units=256, period=160, burst=4) \
      .add_thread(threads.PeriodicWorkThread, {'shares': 250},
                  ready_time=500, units=20, period=160, burst=4) \
      .add_thread(threads.Thread, {'shares': 1600}) \
      .add_thread(threads.Thread, {'shares': 100}) \
      .add_thread(threads.Thread, {'shares': 100})


def main():
    """Run the test."""
    # Create the logger.
    log_file_name = sys.argv[1] if len(sys.argv) > 1 else '-'
    log_to_file = log_file_name != '-'
    with open(log_file_name, 'xb') if log_to_file else sys.stdout.buffer as log_file:
        binary_log = binarylog.BinaryLog(log_file)

        # Create and run the world.
        the_world = world.World(1, KERNEL.module, binary_log, local_timer_scheduling=True)
        while the_world.step() <= 2000:
            pass

        the_world.log_statistics()


if __name__ == '__main__':
    main()
