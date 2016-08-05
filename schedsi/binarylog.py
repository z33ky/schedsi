#!/usr/bin/env python3
"""Defines the BinaryLog."""

import collections
import enum
import msgpack

#types emulating schedsi classes for the textlog
Core = collections.namedtuple('Core', 'uid')
Thread = collections.namedtuple('Thread', 'tid module')

#since we deal with string here that we need to decode
#a proper class is required
class Module: #pylint: disable=too-few-public-methods
    """Emulation for module.Module."""

    def __init__(self, name):
        """Create a Module."""
        self.name = name.decode("utf-8")

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
        thing = {'type': EntryType.event.value, 'cpu': encode(thing.cpu),
                 'time': thing.time, 'event': thing.event.value}
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
    if entry[b'type'] == EntryType.event.value:
        return GenericEvent(Core(entry[b'cpu'][b'uid']), entry[b'time'], entry[b'event'])
    return None

def decode_module(entry, key=b'module'):
    """Extract a Module from a dict-entry.  """
    return Module(entry[key][b'name'])

def decode_thread(entry, key=b'thread'):
    """Extract a Thread from a dict-entry."""
    thread = entry[key]
    return Thread(thread[b'tid'], decode_module(thread))

def replay(binary, log):
    """Play a MessagePack file to a TextLog."""
    for entry in msgpack.Unpacker(binary):
        event = decode_generic_event(entry)
        if event:
            if event.event == Event.schedule_none.value:
                log.schedule_none(*event.as_args(), decode_module(entry))
            elif event.event == Event.schedule_thread.value:
                log.schedule_thread(*event.as_args(), decode_thread(entry))
            elif event.event == Event.context_switch.value:
                log.context_switch(*event.as_args(),
                                   decode_module(entry, b'module_from'),
                                   decode_module(entry, b'module_to'),
                                   entry[b'cost'])
            elif event.event == Event.context_switch_fail.value:
                log.context_switch_fail(*event.as_args(),
                                        decode_module(entry, b'module_from'),
                                        decode_module(entry, b'module_to'),
                                        entry[b'cost'])
            elif event.event == Event.thread_execute.value:
                log.thread_execute(*event.as_args(), decode_thread(entry), entry[b'runtime'])
            elif event.event == Event.thread_yield.value:
                log.thread_yield(*event.as_args(), decode_thread(entry))
            elif event.event == Event.cpu_idle.value:
                log.cpu_idle(*event.as_args(), entry[b'idle_time'])
            elif event.event == Event.timer_interrupt.value:
                log.timer_interrupt(*event.as_args())
            else:
                print("Unknown event:", event)
        else:
            print("Unknown entry:", entry)
