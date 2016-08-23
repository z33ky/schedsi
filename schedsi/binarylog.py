#!/usr/bin/env python3
"""Defines the BinaryLog."""

import collections
import enum
import msgpack

#types emulating schedsi classes for the textlog
Core = collections.namedtuple('Core', 'uid')
Thread = collections.namedtuple('Thread', 'tid module')
Module = collections.namedtuple('Module', 'name')

class GenericEvent: #pylint: disable=too-few-public-methods
    """A generic events.

    It consists of a cpu, time and event-type.
    """

    def __init__(self, cpu, time, event):
        """Create a generic event."""
        self.cpu = cpu
        self.time = time
        self.event = event

    def as_args(self):
        """Converts self to a tuple suitable for calling Log functions."""
        return (self.cpu, self.time)

EntryType = enum.Enum('EntryType', 'event')
Event = enum.Enum('Event', [
    'schedule_none',
    'schedule_thread',
    'context_switch',
    'context_switch_fail',
    'thread_execute',
    'thread_yield',
    'cpu_idle',
    'timer_interrupt'
])

def encode(thing):
    """Encode emulation types and GenericEvent to a dict."""
    from schedsi import cpu, module, threads

    if isinstance(thing, cpu.Core):
        thing = {'uid': thing.uid}
    elif isinstance(thing, module.Module):
        thing = {'name': thing.name}
    elif isinstance(thing, threads.Thread):
        thing = {'module': thing.module, 'tid': thing.tid}
    elif isinstance(thing, GenericEvent):
        thing = {'type': EntryType.event.name, 'cpu': encode(thing.cpu),
                 'time': thing.time, 'event': thing.event.name}
    return thing

def encode_event(cpu, time, event, args=None):
    """Encode a generic event to a dict.

    args can contain additional parameters to put in the dict.
    """
    encoded = encode(GenericEvent(cpu, time, event))
    if args:
        encoded.update(args)
    return encoded

class BinaryLog:
    """Binary logger using MessagePack."""
    def __init__(self, stream):
        """Create a BinaryLog."""
        self.stream = stream
        self.packer = msgpack.Packer(default=encode)

    def _write(self, data):
        """Write data to the MessagePack file."""
        self.stream.write(self.packer.pack(data))

    def schedule_none(self, cpu, time, module):
        """Log an "no threads to schedule" event."""
        self._write(encode_event(cpu, time, Event.schedule_none, {'module': module}))

    def schedule_thread(self, cpu, time, thread):
        """Log an successful scheduling event."""
        self._write(encode_event(cpu, time, Event.schedule_thread, {'thread': thread}))

    def context_switch(self, cpu, time, module_from, module_to, cost):
        """Log an "timeout while scheduling" event."""
        self._write(encode_event(cpu, time, Event.context_switch,
                                 {'module_from': module_from, 'module_to': module_to, 'cost': cost}))

    def context_switch_fail(self, cpu, time, module_from, module_to, cost):
        """Log an "timeout while scheduling" event."""
        self._write(encode_event(cpu, time, Event.context_switch_fail,
                                 {'module_from': module_from, 'module_to': module_to, 'cost': cost}))

    def thread_execute(self, cpu, time, thread, runtime):
        """Log an thread execution event."""
        self._write(encode_event(cpu, time, Event.thread_execute,
                                 {'thread': thread, 'runtime': runtime}))

    def thread_yield(self, cpu, time, thread):
        """Log an thread yielded event."""
        self._write(encode_event(cpu, time, Event.thread_yield, {'thread': thread}))

    def cpu_idle(self, cpu, time, idle_time):
        """Log an CPU idle event."""
        self._write(encode_event(cpu, time, Event.cpu_idle, {'idle_time': idle_time}))

    def timer_interrupt(self, cpu, time):
        """Log an timer interrupt event."""
        self._write(encode_event(cpu, time, Event.timer_interrupt))

def decode_generic_event(entry):
    """Convert a dict-entry to a GenericEvent.

    Returns None on failure.
    """
    if entry['type'] == EntryType.event.name:
        return GenericEvent(Core(entry['cpu']['uid']), entry['time'], entry['event'])
    return None

def decode_module(entry, key='module'):
    """Extract a Module from a dict-entry.  """
    return Module(entry[key]['name'])

def decode_thread(entry, key='thread'):
    """Extract a Thread from a dict-entry."""
    thread = entry[key]
    return Thread(thread['tid'], decode_module(thread))

def replay(binary, log):
    """Play a MessagePack file to a TextLog."""
    for entry in msgpack.Unpacker(binary, encoding='utf-8'):
        event = decode_generic_event(entry)
        if event:
            if event.event == Event.schedule_none.name:
                log.schedule_none(*event.as_args(), decode_module(entry))
            elif event.event == Event.schedule_thread.name:
                log.schedule_thread(*event.as_args(), decode_thread(entry))
            elif event.event == Event.context_switch.name:
                log.context_switch(*event.as_args(),
                                   decode_module(entry, 'module_from'),
                                   decode_module(entry, 'module_to'),
                                   entry['cost'])
            elif event.event == Event.context_switch_fail.name:
                log.context_switch_fail(*event.as_args(),
                                        decode_module(entry, 'module_from'),
                                        decode_module(entry, 'module_to'),
                                        entry['cost'])
            elif event.event == Event.thread_execute.name:
                log.thread_execute(*event.as_args(), decode_thread(entry), entry['runtime'])
            elif event.event == Event.thread_yield.name:
                log.thread_yield(*event.as_args(), decode_thread(entry))
            elif event.event == Event.cpu_idle.name:
                log.cpu_idle(*event.as_args(), entry['idle_time'])
            elif event.event == Event.timer_interrupt.name:
                log.timer_interrupt(*event.as_args())
            else:
                print("Unknown event:", event)
        else:
            print("Unknown entry:", entry)
