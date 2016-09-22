#!/usr/bin/env python3
"""Defines the :class:`BinaryLog` and the :func:`replay` function."""

import collections
import enum
import msgpack

_EntryType = enum.Enum('EntryType', ['event', 'thread_statistics', 'cpu_statistics'])
_Event = enum.Enum('Event', [
    'init_core',
    'context_switch',
    'thread_execute',
    'thread_yield',
    'cpu_idle',
    'timer_interrupt'
])

_GenericEvent = collections.namedtuple('_GenericEvent', 'cpu event')

def _encode_cpu(cpu):
    """Encode a :class:`Core` to a :obj:`dict`."""
    return {
        'uid': cpu.uid,
        'status': {'current_time': cpu.status.current_time}
    }

def _encode_contexts(contexts):
    """Encode a :class:`_Context` to a :obj:`dict`."""
    return [{'thread': _encode_thread(c.thread)} for c in contexts]

def _encode_module(module):
    """Encode a :class:`Module` to a :obj:`dict`."""
    return {'name': module.name}

def _encode_thread(thread):
    """Encode a :class:`Thread` to a :obj:`dict`."""
    return {'module': _encode_module(thread.module), 'tid': thread.tid}

def _encode_event(cpu, event, args=None):
    """Create a :class:`_GenericEvent`.

    `args` can contain additional parameters to put in the :obj:`dict`.
    """
    encoded = {'cpu': _encode_cpu(cpu), 'event': event, 'type': _EntryType.event.name}
    if not args is None:
        encoded.update(args)
    return encoded

def _encode_ctxsw(cpu, thread_to, time, required):
    """Encode a context switching event to a :obj:`dict`."""
    module_to = thread_to.module
    module_from = cpu.status.contexts[-1].thread.module
    if module_to == module_from:
        direction = 'own child'
        if len(cpu.status.contexts) >= 2:
            if cpu.status.contexts[-2].thread == thread_to:
                direction = 'own parent'
    elif cpu.status.contexts[0].thread == thread_to:
        direction = 'kernel'
    elif module_from.parent == module_to:
        direction = 'parent'
    elif module_to.parent == module_from:
        direction = 'child'
    else:
        raise RuntimeError('Unable to determine context switch direction')
    return _encode_event(cpu, _Event.context_switch.name,
                         {
                             'direction': direction, 'thread_to': _encode_thread(thread_to),
                             'time': time, 'required': required
                         })

def _encode_coreinit(cpu):
    """Encode a init_core event to a :obj:`dict`."""
    return _encode_event(cpu, _Event.init_core.name,
                         {'context': _encode_contexts(cpu.status.contexts)})

class BinaryLog:
    """Binary logger using MessagePack."""
    def __init__(self, stream):
        """Create a :class:`BinaryLog`."""
        self.stream = stream
        self.packer = msgpack.Packer()

    def _write(self, data):
        """Write data to the MessagePack file."""
        self.stream.write(self.packer.pack(data))

    def _encode(self, cpu, event, args=None):
        """Encode an event and write data to the MessagePack file.

        See :func:`_encode_event`."""
        self._write(_encode_event(cpu, event.name, args))

    def init_core(self, cpu):
        """Register a :class:`Core`."""
        self._write(_encode_coreinit(cpu))

    def context_switch(self, cpu, thread_to, time, required):
        """Log an context switch event."""
        self._write(_encode_ctxsw(cpu, thread_to, time, required))

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

    def thread_statistics(self, stats):
        """Log thread statistics."""
        self._write({'type': _EntryType.thread_statistics.name, 'stats': stats})

    def cpu_statistics(self, stats):
        """Log CPU statistics."""
        self._write({'type': _EntryType.cpu_statistics.name, 'stats': list(stats)})

#types emulating schedsi classes for other logs
_CPUContext = collections.namedtuple('_CPUContext', 'thread')
_Core = collections.namedtuple('_Core', 'uid status')

#namedtuples are immutable, but the following classes require mutable fields

class _Module: # pylint: disable=too-few-public-methods
    """A :class:`module.Module <schedsi.module.Module>` emulation class."""
    def __init__(self, name):
        """Create a :class:`_Module`."""
        self.name = name
        self.parent = None

class _CPUStatus: # pylint: disable=too-few-public-methods
    """A :class:`cpu._Status <schedsi.cpu._Status>` emulation class."""
    def __init__(self, current_time):
        """Create a :class:`_CPUStatus`."""
        self.current_time = current_time
        self.contexts = None

class _Thread: # pylint: disable=too-few-public-methods
    """A :class:`threads.Thread <schedsi.threads.Thread>` emulation class."""
    def __init__(self, tid, module):
        """Create a :class:`_Thread`."""
        self.tid = tid
        self.module = module

def _decode_contexts(entries):
    """Extract :class:`_CPUContexts <_CPUContext>` from a :obj:`dict`-entry."""
    return [_CPUContext(_decode_thread(entry['thread'])) for entry in entries]

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
    return _CPUStatus(entry['current_time'])

def _decode_thread(entry):
    """Extract a :class:`_Thread` from a :obj:`dict`-entry.

    Returns :obj:`None` if `entry` is :obj:`None`.
    """
    if not entry:
        return None
    return _Thread(entry['tid'], _decode_module(entry['module']))

def _decode_module(entry):
    """Extract a :class:`_Module` from a :obj:`dict`-entry.

    Returns :obj:`None` if `entry` is :obj:`None`.
    """
    if not entry:
        return None
    return _Module(entry['name'])

def _decode_ctxsw(cpu, entry):
    """Extract context switch arguments from a :obj:`dict`-entry.

    Returns a tuple (tuple for arguments, direction),
    where direction is a string specifying the kind of switch:
        parent, child, kernel
    """
    thread_to = _decode_thread(entry['thread_to'])
    direction = entry['direction']
    module_from = cpu.status.contexts[-1].thread.module

    if direction == 'child':
        thread_to.module.parent = module_from
    elif direction == 'parent':
        thread_to = cpu.status.contexts[-2].thread
    elif direction.startswith('own '):
        if thread_to.module.name != module_from.name:
            raise RuntimeError('Context switch to ' + direction + ' failed verification')
        thread_to.module = module_from
        #remove own prefix
        direction = direction[4:]

    return (cpu, thread_to, entry['time'], entry['required']), direction

def replay(binary, log):
    """Play a MessagePack file to another log."""
    contexts = {}
    for entry in msgpack.Unpacker(binary, read_size=16*1024, encoding='utf-8', use_list=False):
        event = _decode_generic_event(entry)
        if not event is None:
            if event.event == _Event.init_core.name:
                if event.cpu.uid in contexts:
                    raise RuntimeError('init_core found twice for same core')
                contexts[event.cpu.uid] = _decode_contexts(entry['context'])

            event.cpu.status.contexts = contexts[event.cpu.uid]

            if event.event == _Event.init_core.name:
                log.init_core(event.cpu)
            elif event.event == _Event.context_switch.name:
                event_args, direction = _decode_ctxsw(event.cpu, entry)
                log.context_switch(*event_args)
                core_contexts = event.cpu.status.contexts
                if direction == 'parent':
                    if len(core_contexts) > 1:
                        core_contexts.pop()
                elif direction == 'child':
                    core_contexts.append(_CPUContext(event_args[1]))
                elif direction == 'kernel':
                    del core_contexts[1:]
                else:
                    raise RuntimeError('Invalid context switch direction ' + direction)
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
        elif entry['type'] == _EntryType.thread_statistics.name:
            log.thread_statistics(entry['stats'])
        elif entry['type'] == _EntryType.cpu_statistics.name:
            log.cpu_statistics(entry['stats'])
        else:
            print("Unknown entry:", entry)
