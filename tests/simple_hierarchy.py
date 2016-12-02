#!/usr/bin/env python3
"""Create a simple hierarchy.

It consists of
    * a kernel with two threads (plus one VCPU thread)
    * a child-module with one thread (plus two VCPU threads)
    * two grandchildren with a total of five threads

Scheduling is done via :class:`RoundRobin` and :class:`SJF`.
"""

from schedsi import hierarchy_builder, schedulers, threads

KERNEL = hierarchy_builder.ModuleBuilder(scheduler=schedulers.RoundRobin.builder(time_slice=10))
TOP_MODULE = KERNEL.add_module(scheduler=schedulers.RoundRobin)
BOTTOM_MODULE_A = TOP_MODULE.add_module(scheduler=schedulers.RoundRobin)
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

KERNEL = KERNEL.module # pylint: disable=redefined-variable-type
TOP_MODULE = TOP_MODULE.module # pylint: disable=redefined-variable-type
BOTTOM_MODULE_A = BOTTOM_MODULE_A.module # pylint: disable=redefined-variable-type
BOTTOM_MODULE_B = BOTTOM_MODULE_B.module # pylint: disable=redefined-variable-type
