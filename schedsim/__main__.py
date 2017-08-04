#!/usr/bin/env python3
"""Run a simulation loaded from a schedsim-file.

The schedsim file format is documented in `schedsim`.
"""

import sys
from schedsi import world
from schedsi.util import hierarchy_builder
from parser import Parser, Symbol
from interpreter import load_log, load_simulation

def append_modules(children, parent):
    """Generate :class:`Module`s from `children` attached to `parent`.

    `parent` may be `None` for the kernel.

    Return the list of generated modules.
    """
    modules = []
    for name, sched, workload, mods in children:
        if parent is not None:
            module = parent.add_module(name, scheduler=sched[0].builder(**sched[1]))
        else:
            module = hierarchy_builder.ModuleBuilder(name, scheduler=sched[0].builder(**sched[1]))

        append_modules(mods, module)

        for thread, tid, kwargs in workload:
            module.add_thread(thread, tid=tid, **kwargs)
        module.add_vcpus()

        modules.append(module)
    return modules

def main():
    """Load and run a simulation."""
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} simulation.schedsim', file=sys.stderr)
        sys.exit(1)

    nodes = (*Parser(open(sys.argv[1], 'r')),)
    # print(repr(nodes))

    sim = load_simulation(nodes)

    if sim['log'] is None:
        sim['log'] = load_log([Symbol('BinaryLog')])

    kernel = append_modules((sim['kernel'],), None)[0]

    logger, logger_finish = sim['log']
    the_world = world.World(1, kernel.module, logger, local_timer_scheduling=sim['local_timer'])
    limit = sim['time_limit']
    try:
        while the_world.step() <= limit:
            pass
    except RuntimeError:
        if not all(thread.is_finished() for thread in kernel.module.all_threads()):
            raise
    logger_finish(the_world)

if __name__ == '__main__':
    main()
