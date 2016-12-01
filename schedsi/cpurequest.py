#!/usr/bin/env python3
"""Defines a :class:`CPURequest`."""

import enum
from schedsi import threads

Type = enum.Enum('Type', ['current_time', 'switch_thread', 'idle', 'execute'])

class Request:
    """A request to the CPU."""

    def __init__(self, rtype, thing):
        """Create a :class:`Request`."""
        if rtype == Type.current_time:
            assert thing is None
        elif rtype == Type.switch_thread:
            assert isinstance(thing, threads.Thread)
        elif rtype == Type.idle:
            assert thing is None
        elif rtype == Type.execute:
            assert thing > 0 or thing == -1
        else:
            assert False
        self.rtype = rtype
        self.thing = thing

    @classmethod
    def current_time(cls):
        """Create a :class:`Request` to get the current time.

        The CPU will not spend any virtual time doing this.
        """
        return cls(Type.current_time, None)

    @classmethod
    def switch_thread(cls, thread):
        """Create a :class:`Request` to switch context."""
        return cls(Type.switch_thread, thread)

    @classmethod
    def idle(cls):
        """Create a :class:`Request` to idle."""
        return cls(Type.idle, None)

    @classmethod
    def execute(cls, amount):
        """Create a :class:`Request` to spend some time executing."""
        return cls(Type.execute, amount)

