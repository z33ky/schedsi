#!/usr/bin/env python3
"""Defines functions to interpret schedsim expressions."""

import io
import sys
from parser import String, Symbol, Tuple
from schedsi import schedulers, threads, log
from .error import InterpreterError
from .util import (check_type, check_tuple_len, get_params, get_single_param, set_once,
                   NodeValueError)

_ADDON_SCHEDULER_CACHE = {}

def load_scheduler(params):
    """Return a (`scheduler`, `kwargs`)-tuple created from `params`.

    `scheduler` is a :class:`Scheduler` and `kwargs` specifies the kwargs-parameter to be passed
    to its initializer.
    """
    check_tuple_len(params, exact=1)
    params = params[0]
    check_tuple_len(params, least=1, len_msg='Missing scheduler name')
    sched_name = check_type(params[0], Symbol).symbol
    sched = getattr(schedulers, sched_name, None)

    if sched is None:
        addon = getattr(schedulers.addons, sched_name, None)
        if addon is None:
            raise InterpreterError(f'Unknown scheduler {sched_name}')

        sched, kwargs = load_scheduler(params[1:])
        sched_name = f'{sched.__name__}With{addon.__name__}'
        cache_key = (addon, sched)
        addon_scheduler = _ADDON_SCHEDULER_CACHE.get(cache_key, None)
        if addon_scheduler is None:
            addon_scheduler = addon.attach(sched_name, sched)
            _ADDON_SCHEDULER_CACHE[cache_key] = addon_scheduler

        return addon_scheduler, kwargs

    kwargs = get_params(params[1:], ())

    return sched, kwargs

def load_thread(params):
    """Return a (`thread`, `kwargs`)-tuple created from `params`.

    `thread` is a :class:`Thread` and `kwargs` specifies the kwargs-parameter to be passed to its
    initializer.
    """
    tid = None
    if len(params) > 0 and type(params[0]) == String:
        tid = params[0].string
        params = params[1:]

    kwargs = get_params(params, ())

    thread = threads.Thread
    if any(param in kwargs.keys() for param in ('period', 'burst')):
        thread = threads.PeriodicWorkThread

    return thread, tid, kwargs

def load_module(nodes):
    """Return a (`name`, `scheduler`, `workload`, `modules`)-tuple created from `nodes`.

    `name` is the name of the module (may be `None`).
    `scheduler` contains a tuple (see :func:`load_scheduler`).
    `workload` contains a list of tuples (see :func:`load_thread`).
    `module` contains a list of tuples (see :func:`load_module`).
    """
    check_type(nodes, Tuple)

    name = None
    if type(nodes[0]) == String:
        name = nodes[0].string
        nodes = nodes[1:]
    scheduler = None
    workload = []
    modules = []

    for node in nodes:
        check_tuple_len(node, least=1,
                        len_msg='Module cannot contain an empty tuple')
        ident = check_type(node[0], Symbol).symbol
        if ident == 'scheduler':
            if scheduler is not None:
                raise InterpreterError('Parameter scheduler already set')
            scheduler = load_scheduler(node[1:])
        elif ident == 'Thread':
            workload.append(load_thread(node[1:]))
        elif ident == 'Module':
            modules.append(load_module(node[1:]))
        else:
            raise NodeValueError(f'Unknown key', node[0])

    if scheduler is None:
        scheduler = schedulers.Single

    return (name, scheduler, workload, modules)

def load_log(nodes):
    """Return a (`logger`, `logger finish function`)-tuple created from `nodes`.

    `logger` is the log-instance.
    `logger finish function` is a function that should be called when the simulation finished.
    """
    log_name = check_type(nodes[0], Symbol).symbol
    kwargs = get_params(nodes[1:], ())

    if log_name == 'TextLog':
        log_file = kwargs.pop('file', None)
        if log_file is None:
            log_file = sys.stdout
        else:
            log_file = open(log_file, 'w')

        args = kwargs.pop('align', None)
        if args is None:
            args = ()
        else:
            args = (log.TextLogAlign(*args),)
        logger = log.TextLog(log_file, *args, time_precision=kwargs.pop('time_precision'))

        def finish(the_world):
            the_world.log_statistics()

        if kwargs:
            raise InterpreterError(f'Unknown TextLog parameters: {(*kwargs.keys(),)}')
    elif log_name == 'BinaryLog':
        log_file = kwargs.pop('file', None)
        if log_file is None:
            log_file = sys.stdout.buffer
        else:
            log_file = open(log_file, 'wb')

        logger = log.BinaryLog(log_file)

        def finish(the_world):
            the_world.log_statistics()

        if kwargs:
            raise InterpreterError(f'Unknown BinaryLog parameters: {(*kwargs.keys(),)}')
    elif log_name == 'GanttLog':
        svg_file = kwargs.pop('file', None)
        if svg_file is None:
            svg_file = io.BytesIO()
        else:
            svg_file = open(svg_file, 'wb')

        params = {}
        #FIXME: param types
        for param in ('draw_scale', 'text_scale', 'name_module'):
            if param in kwargs:
                params[param] = kwargs.pop(param)

        time_scale = kwargs.pop('time_scale', None)
        if time_scale is not None:
            log.GanttLog.time_scale = time_scale
        logger = log.GanttLog(**params)

        def finish(_the_world):
            logger.write(svg_file)
            if type(svg_file) == io.BytesIO:
                sys.stdout.buffer.write(svg_file.getvalue())

        if kwargs:
            raise InterpreterError(f'Unknown GanttLog parameters: {(*kwargs.keys(),)}')
    else:
        raise InterpreterError(f'Unknown log type {log_name}')

    return logger, finish

def load_simulation(nodes):
    """Return a `dict` describing the simulation declared in `nodes`."""
    if len(nodes) != 1:
        raise InterpreterError('There must be exactly one root node')
    check_tuple_len(nodes[0], least=1,
                    type_msg='Root node must be a tuple',
                    len_msg='Root node must be a tuple with Simulation key')
    if check_type(nodes[0][0], Symbol).symbol != 'Simulation':
        raise InterpreterError('Root node must be a tuple with Simulation key')

    sim = {}

    for node in nodes[0][1:]:
        check_tuple_len(node, least=1,
                        type_msg='Simulation can only contain tuple-values',
                        len_msg='Simulation cannot contain empty tuples')
        ident = node[0]
        ident = check_type(ident, Symbol).symbol
        if ident == 'log':
            set_once(sim, 'log', load_log(node[1:]))
        elif ident == 'local_timer':
            key, value = get_single_param(node, bool)
            assert key == ident
            set_once(sim, 'local_timer', value)
        elif ident == 'time_limit':
            key, value = get_single_param(node, float)
            assert key == ident
            set_once(sim, 'time_limit', value)
        elif ident == 'Module':
            set_once(sim, 'kernel', load_module(node[1:]),
                     'Simulation cannot contain more than one module')
        else:
            raise NodeValueError(f'Unknown key', node[0])

    return sim
