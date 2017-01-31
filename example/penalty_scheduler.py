#!/usr/bin/env python3
"""Sample/test for schedsi.

The test consists of a kernel using the round robin scheduler
to schedule two threads - one continuously executing,
one with periodic bursts.
This example does not use the local timers feature.
"""

# pylint: disable=duplicate-code
import sys
from schedsi import (binarylog, hierarchy_builder, penalty_scheduler_addon, schedulers, threads,
                     world)

PRR = penalty_scheduler_addon.PenaltySchedulerAddon.attach("PRR", schedulers.RoundRobin)

PMLFQ = penalty_scheduler_addon.PenaltySchedulerAddon.attach("PMLFQ", schedulers.MLFQ)

# Create a hierarchy of a kernel, a child module and two grand-children.
KERNEL = hierarchy_builder.ModuleBuilder(scheduler=PRR.builder(time_slice=9,
                                                               override_time_slice=10))
TOP_MODULE = KERNEL.add_module(scheduler=PMLFQ.builder(level_time_slices=[10, 8, 6, 5],
                                                       priority_boost_time=30))
BOTTOM_MODULE_A = TOP_MODULE.add_module(scheduler=PRR.builder(time_slice=7))
BOTTOM_MODULE_B = TOP_MODULE.add_module(scheduler=schedulers.SJF)

KERNEL.add_thread(threads.Thread, units=50) \
      .add_thread(threads.PeriodicWorkThread, ready_time=5, units=50, period=20, burst=5) \
      .add_vcpus()

TOP_MODULE.add_thread(threads.Thread, units=25).add_vcpus()

BOTTOM_MODULE_A.add_thread(threads.Thread, units=10) \
               .add_thread(threads.Thread, ready_time=50, units=25) \
               .add_vcpus()

BOTTOM_MODULE_B.add_thread(threads.PeriodicWorkThread, units=10, period=10, burst=2) \
               .add_thread(threads.PeriodicWorkThread, period=10, burst=2) \
               .add_thread(threads.Thread, ready_time=10, units=10) \
               .add_vcpus()


def main():
    """Run the test."""
    # Create the logger.
    log_file_name = sys.argv[1] if len(sys.argv) > 1 else '-'
    log_to_file = log_file_name != '-'
    with open(log_file_name, 'xb') if log_to_file else sys.stdout.buffer as log_file:
        binary_log = binarylog.BinaryLog(log_file)

        # Create and run the world.
        the_world = world.World(1, KERNEL.module, binary_log, local_timer_scheduling=False)
        while the_world.step() <= 400:
            pass

        the_world.log_statistics()


if __name__ == '__main__':
    main()
