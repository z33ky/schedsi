#!/usr/bin/env python3
"""Defines the BinaryLog."""

import collections
import enum
import msgpack

#types emulating schedsi classes for the textlog
CPUContext = collections.namedtuple('CPUContext', 'module thread')
CPUStatus = collections.namedtuple('CPUStatus', 'current_time context')
Core = collections.namedtuple('Core', 'uid status')
Thread = collections.namedtuple('Thread', 'tid module')
Module = collections.namedtuple('Module', 'name')
GenericEvent = collections.namedtuple('GenericEvent', 'cpu event')

EntryType = enum.Enum('EntryType', 'event')
Event = enum.Enum('Event', [
    'module_yield',
    'schedule_thread',
    'context_switch',
    'thread_execute',
    'thread_yield',
    'kernel_yield',
    'cpu_idle',
    'timer_interrupt'
])

def encode(thing):
    """Encode emulation types and GenericEvent to a dict."""
    from schedsi import cpu, module, threads

    if isinstance(thing, cpu._Context): # pylint: disable=protected-access
        thing = {'thread': encode(thing.thread), 'module': encode(thing.module)}
    elif isinstance(thing, cpu._Status): # pylint: disable=protected-access
        thing = {'current_time': encode(thing.current_time), 'context': encode(thing.context)}
    elif isinstance(thing, cpu.Core):
        thing = {'uid': thing.uid, 'status': encode(thing.status)}
    elif isinstance(thing, module.Module):
        thing = {'name': thing.name}
    elif isinstance(thing, threads.Thread):
        thing = {'module': encode(thing.module), 'tid': thing.tid}
    elif isinstance(thing, GenericEvent):
        thing = {'type': EntryType.event.name, 'cpu': encode(thing.cpu),
                 'event': thing.event.name}
    return thing

def encode_event(cpu, event, args=None):
    """Encode a generic event to a dict.

    args can contain additional parameters to put in the dict.
    """
    encoded = encode(GenericEvent(cpu, event))
    if args:
        encoded.update(args)
    return encoded

def encode_ctxsw(event, cpu, module_to, time, required):
    """Encode a context switching event to a dict."""
    module_from = cpu.status.context.module
    if module_from.parent == module_to:
        direction = 'parent'
    elif module_to.parent == module_from:
        direction = 'child'
    else:
        direction = 'unrelated'
    return encode_event(cpu, event,
                        {'direction': direction, 'module_to': module_to,
                         'time': time, 'required': required})

class BinaryLog:
    """Binary logger using MessagePack."""
    def __init__(self, stream):
        """Create a BinaryLog."""
        self.stream = stream
        self.packer = msgpack.Packer(default=encode)

    def _write(self, data):
        """Write data to the MessagePack file."""
        self.stream.write(self.packer.pack(data))

    def module_yield(self, cpu, module_to, time, required):
        """Log an "module yields (usually to parent)" event."""
        self._write(encode_ctxsw(Event.module_yield, cpu, module_to, time, required))

    def schedule_thread(self, cpu):
        """Log an successful scheduling event."""
        self._write(encode_event(cpu, Event.schedule_thread))

    def context_switch(self, cpu, module_to, time, required):
        """Log an context switch event."""
        self._write(encode_ctxsw(Event.context_switch, cpu, module_to, time, required))

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        self._write(encode_event(cpu, Event.thread_execute, {'runtime': runtime}))

    def thread_yield(self, cpu):
        """Log an thread yielded event."""
        self._write(encode_event(cpu, Event.thread_yield))

    def kernel_yield(self, cpu):
        """Log a kernel yield event."""
        self._write(encode_event(cpu, Event.kernel_yield))

    def cpu_idle(self, cpu, idle_time):
        """Log an CPU idle event."""
        self._write(encode_event(cpu, Event.cpu_idle, {'idle_time': idle_time}))

    def timer_interrupt(self, cpu):
        """Log an timer interrupt event."""
        self._write(encode_event(cpu, Event.timer_interrupt))

def decode_generic_event(entry):
    """Convert a dict-entry to a GenericEvent.

    Returns None on failure.
    """
    if entry['type'] == EntryType.event.name:
        return GenericEvent(decode_core(entry), entry['event'])
    return None

def decode_core(entry):
    """Extract a Core from a dict-entry."""
    core = entry['cpu']
    return Core(core['uid'], decode_status(core['status']))

def decode_status(entry):
    """Extract CPUStatus from a dict-entry."""
    return CPUStatus(entry['current_time'], decode_context(entry['context']))

def decode_context(entry):
    """Extract CPUContext from a dict-entry."""
    return CPUContext(decode_module(entry['module']), decode_thread(entry['thread']))

def decode_thread(entry):
    """Extract a Thread from a dict-entry.

    Returns None if entry is None."""
    if not entry:
        return None
    return Thread(entry['tid'], decode_module(entry['module']))

def decode_module(entry):
    """Extract a Module from a dict-entry.

    Returns None if entry is None."""
    if not entry:
        return None
    return Module(entry['name'])

def decode_ctxsw(entry):
    """Extract context switch arguments from a dict-entry."""
    return (decode_module(entry['module_to']), entry['time'], entry['required'])

def replay(binary, log):
    """Play a MessagePack file to a TextLog."""
    for entry in msgpack.Unpacker(binary, encoding='utf-8'):
        event = decode_generic_event(entry)
        if event:
            if event.event == Event.module_yield.name:
                log.module_yield(event.cpu, *decode_ctxsw(entry))
            elif event.event == Event.schedule_thread.name:
                log.schedule_thread(event.cpu)
            elif event.event == Event.context_switch.name:
                log.context_switch(event.cpu, *decode_ctxsw(entry))
            elif event.event == Event.thread_execute.name:
                log.thread_execute(event.cpu, entry['runtime'])
            elif event.event == Event.thread_yield.name:
                log.thread_yield(event.cpu)
            elif event.event == Event.kernel_yield.name:
                log.kernel_yield(event.cpu)
            elif event.event == Event.cpu_idle.name:
                log.cpu_idle(event.cpu, entry['idle_time'])
            elif event.event == Event.timer_interrupt.name:
                log.timer_interrupt(event.cpu)
            else:
                print("Unknown event:", event)
        else:
            print("Unknown entry:", entry)
