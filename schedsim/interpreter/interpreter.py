#!/usr/bin/env python3
"""Defines functions to interpret schedsim expressions."""

import collections
import inspect
import itertools
import io
import sys
import typing
from parser import String, Symbol, Tuple
from schedsi import schedulers, threads, log
from .error import InterpreterError
from .util import (check_type, check_tuple_len, get_param_keys, get_params, get_single_param,
                   get_value, set_once, NodeValueError)

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

class Sentinel: pass
sentinel = Sentinel()

# primitives as far as util.get_value is concerned
ARG_PRIMITIVES = (bool, float, int, str, tuple, list)
def get_arg_value(arg, param_type):
    """Extract a value from `arg` for a parameter of type `param_type`.

    `param_type` may be `None`, in which case it tries to parse it as any of
    `bool`, `int`, `float` or a `str`. See also :func:`util.get_value`.
    """
    if param_type not in ARG_PRIMITIVES and \
       isinstance(getattr(param_type, '__init__', None), collections.Callable):
        init_spec = inspect.getfullargspec(param_type.__init__)
        if init_spec.varargs is not None or init_spec.varkw is not None:
            raise RuntimeError('get_arg_value() doesn\'t support varargs, '
                               f'required for {param_type.__name__}')
        if init_spec.kwonlyargs:
            raise RuntimeError('get_arg_value() doesn\'t support kwargs, '
                               f'required for {param_type.__name__}')

        params = []
        args = iter(arg)
        num_nondefault = len(init_spec.args[1:]) - len(init_spec.defaults or ())
        defaults = itertools.chain(itertools.repeat(sentinel, num_nondefault), init_spec.defaults)
        for param, default in zip(init_spec.args[1:], defaults):
            tp = init_spec.annotations.get(param, None)
            arg = next(args, sentinel)
            if arg is sentinel:
                if default is sentinel:
                    raise InterpreterError(f'Must specify parameter "{param}" '
                                           f'for {param_type.__name__}')
                arg = default
            else:
                arg = get_value(arg, tp)
            params.append(arg)

        return param_type(*params)

    if issubclass(param_type, typing.Sequence):
        return get_value(arg, param_type.__args__)

    return get_value(arg, param_type)

def load_log(nodes):
    """Return a (`logger`, `logger finish function`)-tuple created from `nodes`.

    `logger` is the log-instance.
    `logger finish function` is a function that should be called when the simulation finished.
    """
    log_name = check_type(nodes[0], Symbol).symbol
    kwargs = get_param_keys(nodes[1:])

    log_cls = getattr(log, log_name, None)
    if not isinstance(log_cls, type):
        raise InterpreterError(f'Unknown log type {log_name}')

    if not isinstance(log_cls.__init__, collections.Callable):
        raise InterpreterError(f'Unknown log type {log_name}')

    init_spec = inspect.getfullargspec(log_cls.__init__)
    if init_spec.varargs is not None or init_spec.varkw is not None:
        raise RuntimeError(f'load_log() doesn\'t support varargs, required by {log_name}')
    assert init_spec.args[0] == 'self'

    log_file = None
    params = []
    num_nondefault = len(init_spec.args[1:]) - len(init_spec.defaults or ())
    defaults = itertools.chain(itertools.repeat(sentinel, num_nondefault), init_spec.defaults)
    for param, default in zip(init_spec.args[1:], defaults):
        param_type = init_spec.annotations.get(param, None)
        if issubclass(param_type, typing.io.IO):
            if param == 'stream':
                assert 'file' not in init_spec.args
                assert 'file' not in init_spec.kwonlyargs
                param = 'file'
        arg = kwargs.pop(param, sentinel)
        if issubclass(param_type, typing.IO):
            if param_type is typing.TextIO:
                mode = 'w'
            elif param_type is typing.BinaryIO:
                mode = 'wb'
            else:
                raise RuntimeError(f'load_log() doesn\'t support {param_type}, '
                                   f'required for {log_name}.__init__')

            if arg is sentinel:
                log_file = sys.stdout
                if mode == 'wb':
                    log_file = log_file.buffer
            else:
                filename = get_value(arg, str)
                log_file = open(filename, mode)

            arg = log_file
        elif arg is sentinel:
            if default is sentinel:
                raise InterpreterError(f'Must specify parameter "{param}" for {log_name}')
            arg = default
        else:
            arg = get_arg_value(arg, param_type)
        params.append(arg)

    kwparams = {}
    for param in init_spec.kwonlyargs:
        arg = kwargs.pop(param, sentinel)
        if arg is sentinel:
            arg = init_spec.kwonlydefaults.get(param, sentinel)
            if arg is sentinel:
                raise InterpreterError(f'Must specify parameter "{param}" for {log_name}')
        else:
            arg = get_value(arg, init_spec.annotations.get(param, ()))
        kwparams[param] = arg

    logger = log_cls(*params, **kwparams)

    def finish(the_world):
        the_world.log_statistics()
    write = getattr(log_cls, 'write', None)
    if isinstance(write, collections.Callable):
        if log_file is None:
            write_spec = inspect.getfullargspec(write)
            if len(write_spec.args[1:]) - len(write_spec.defaults or ()) > 1:
                raise RuntimeError('load_log() requires exactly 1 parameter to write() '
                                   f'for {log_name}')
            param_type = next(iter(write_spec.annotations.values()))
            if param_type is typing.TextIO:
                mode = 'w'
            elif param_type is typing.BinaryIO:
                mode = 'wb'
            else:
                raise RuntimeError(f'load_log() doesn\'t support {param_type}, '
                                   f'required for {log_name}.write()')
            filename = kwargs.pop('file', None)
            if filename is None:
                log_file = sys.stdout
                if mode == 'wb':
                    log_file = log_file.buffer
            else:
                filename = get_value(filename, str)
                log_file = open(filename, mode)
        def finish(the_world):
            the_world.log_statistics()
            logger.write(log_file)

    if kwargs:
        raise InterpreterError(f'Unknown {log_name} parameters: {", ".join(kwargs.keys())}')

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
