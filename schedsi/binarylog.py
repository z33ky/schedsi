#!/usr/bin/env python3
"""Defines the :class:`BinaryLog` and the :func:`replay` function."""

import collections
import enum
import msgpack

_EntryType = enum.Enum('EntryType', 'event')
_Event = enum.Enum('Event', [
    'schedule_thread',
    'context_switch',
    'thread_execute',
    'thread_yield',
    'cpu_idle',
    'timer_interrupt'
])

_GenericEvent = collections.namedtuple('_GenericEvent', 'cpu event')

def _get_from_class(thing, keys):
    """Returns a :obj:`dict` with all the keys from `thing`."""
    return _get_from_dict(thing.__dict__, keys)

def _get_from_tuple(thing, keys):
    """Returns a :obj:`dict` with all the keys from `thing`."""
    return _get_from_dict(dict(thing._asdict()), keys)

def _get_from_dict(thing, keys):
    """Returns a :obj:`dict` with all the keys from `thing`."""
    return {k: thing[k] for k in keys}

def _encode(thing):
    """Encode schedsi types and :class:`_GenericEvent` to a :obj:`dict`."""
    from schedsi import cpu, module, threads

    if isinstance(thing, cpu._Context): # pylint: disable=protected-access
        thing = _get_from_class(thing, ['thread', 'module'])
    elif isinstance(thing, cpu._Status): # pylint: disable=protected-access
        thing = _get_from_class(thing, ['current_time', 'context'])
    elif isinstance(thing, cpu.Core):
        thing = _get_from_class(thing, ['uid', 'status'])
    elif isinstance(thing, module.Module):
        thing = _get_from_class(thing, ['name'])
    elif isinstance(thing, threads.Thread):
        thing = _get_from_class(thing, ['module', 'tid'])
    elif isinstance(thing, _GenericEvent):
        thing = _get_from_tuple(thing, ['cpu', 'event'])
        thing['type'] = _EntryType.event.name
    return thing

def _encode_event(cpu, event, args=None):
    """Create a :class:`_GenericEvent`.

    `args` can contain additional parameters to put in the :obj:`dict`.
    """
    encoded = _encode(_GenericEvent(cpu, event))
    if not args is None:
        encoded.update(args)
    return encoded

def _encode_ctxsw(cpu, module_to, time, required):
    """Encode a context switching event to a :obj:`dict`."""
    module_from = cpu.status.context.module
    if module_from is None:
        assert module_to.parent is None
        direction = 'kernel'
    #parent direction weights more than kernel
    elif module_from.parent == module_to:
        direction = 'parent'
    elif module_to.parent is None:
        direction = 'kernel'
    elif module_to.parent == module_from:
        direction = 'child'
    else:
        direction = 'unrelated'
    return _encode_event(cpu, _Event.context_switch.name,
                         {'direction': direction, 'module_to': module_to,
                          'time': time, 'required': required})

class BinaryLog:
    """Binary logger using MessagePack."""
    def __init__(self, stream):
        """Create a :class:`BinaryLog`."""
        self.stream = stream
        self.packer = msgpack.Packer(default=_encode)

    def _write(self, data):
        """Write data to the MessagePack file."""
        self.stream.write(self.packer.pack(data))

    def _encode(self, cpu, event, args=None):
        """Encode an event and write data to the MessagePack file.

        See :func:`_encode_event`."""
        self._write(_encode_event(cpu, event.name, args))

    def schedule_thread(self, cpu):
        """Log an successful scheduling event."""
        self._encode(cpu, _Event.schedule_thread)

    def context_switch(self, cpu, module_to, time, required):
        """Log an context switch event."""
        self._write(_encode_ctxsw(cpu, module_to, time, required))

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        self._encode(cpu, _Event.thread_execute, {'runtime': runtime})

    def thread_yield(self, cpu):
        """Log an thread yielded event."""
        self._encode(cpu, _Event.thread_yield)

    def cpu_idle(self, cpu, idle_time):
        """Log an CPU idle event."""
        self._encode(cpu, _Event.cpu_idle, {'idle_time': idle_time})

    def timer_interrupt(self, cpu):
        """Log an timer interrupt event."""
        self._encode(cpu, _Event.timer_interrupt)

#types emulating schedsi classes for other logs
_CPUContext = collections.namedtuple('_CPUContext', 'module thread')
_CPUStatus = collections.namedtuple('_CPUStatus', 'current_time context')
_Core = collections.namedtuple('_Core', 'uid status')
_Thread = collections.namedtuple('_Thread', 'tid module')

#this is not a namedtuple because we want parent to be mutable when decoding
class _Module: # pylint: disable=too-few-public-methods
    """A :class:`module.Module <schedsi.module.Module>` emulation class."""
    def __init__(self, name):
        """Create a :class:`_Module`."""
        self.name = name
        self.parent = None

def _decode_generic_event(entry):
    """Convert a :obj:`dict-entry` to a :class:`_GenericEvent`.

    Returns :obj:`None` on failure.
    """
    if entry['type'] == _EntryType.event.name:
        return _GenericEvent(_decode_core(entry), entry['event'])
    return None

def _decode_core(entry):
    """Extract a :class:`_Core` from a :obj:`dict`-entry."""
    core = entry['cpu']
    return _Core(core['uid'], _decode_status(core['status']))

def _decode_status(entry):
    """Extract :class:`_CPUStatus` from a :obj:`dict`-entry."""
    return _CPUStatus(entry['current_time'], _decode_context(entry['context']))

def _decode_context(entry):
    """Extract :class:`_CPUContext` from a :obj:`dict`-entry."""
    return _CPUContext(_decode_module(entry['module']), _decode_thread(entry['thread']))

def _decode_thread(entry):
    """Extract a :class:`_Thread` from a :obj:`dict`-entry.

    Returns :obj:`None` if `entry` is :obj:`None`."""
    if not entry:
        return None
    return _Thread(entry['tid'], _decode_module(entry['module']))

def _decode_module(entry):
    """Extract a :class:`_Module` from a :obj:`dict`-entry.

    Returns :obj:`None` if `entry` is :obj:`None`."""
    if not entry:
        return None
    return _Module(entry['name'])

def _decode_ctxsw(cpu, entry):
    """Extract context switch arguments from a :obj:`dict`-entry."""
    module_to = _decode_module(entry['module_to'])
    direction = entry['direction']
    if direction == 'parent':
        cpu.status.context.module.parent = module_to
        module_to.parent = _Module(None)
    elif direction == 'child':
        module_to.parent = cpu.status.context.module
    elif direction == 'unrelated':
        module_to.parent = _Module(None)
    else:
        assert direction == 'kernel'
    return (cpu, module_to, entry['time'], entry['required'])

def replay(binary, log):
    """Play a MessagePack file to another log."""
    for entry in msgpack.Unpacker(binary, encoding='utf-8'):
        event = _decode_generic_event(entry)
        if not event is None:
            if event.event == _Event.schedule_thread.name:
                log.schedule_thread(event.cpu)
            elif event.event == _Event.context_switch.name:
                log.context_switch(*_decode_ctxsw(event.cpu, entry))
            elif event.event == _Event.thread_execute.name:
                log.thread_execute(event.cpu, entry['runtime'])
            elif event.event == _Event.thread_yield.name:
                log.thread_yield(event.cpu)
            elif event.event == _Event.cpu_idle.name:
                log.cpu_idle(event.cpu, entry['idle_time'])
            elif event.event == _Event.timer_interrupt.name:
                log.timer_interrupt(event.cpu)
            else:
                print("Unknown event:", event)
        else:
            print("Unknown entry:", entry)
