#!/usr/bin/env python3
"""Defines a :class:`Request`."""

import enum
import numbers
from schedsi.cpu import context

Type = enum.Enum('Type', ['current_time', 'resume_chain', 'idle', 'execute', 'timer'])


class Request:
    """A request to the CPU."""

    def __init__(self, rtype, arg):
        """Create a :class:`Request`."""
        if rtype == Type.current_time:
            assert arg is None
        elif rtype == Type.resume_chain:
            assert isinstance(arg, context.Chain)
        elif rtype in (Type.idle, Type.execute, Type.timer):
            assert arg is None or isinstance(arg, numbers.Rational) and arg > 0
        else:
            assert False, 'Unknown Type'
        self.rtype = rtype
        self.arg = arg

    @classmethod
    def current_time(cls):
        """Create a :class:`Request` to get the current time.

        The CPU will not spend any virtual time doing this.
        """
        return cls(Type.current_time, None)

    @classmethod
    def resume_chain(cls, chain):
        """Create a :class:`Request` to resume a :class:`context.Chain <schedsi.context.Chain>`."""
        return cls(Type.resume_chain, chain)

    @classmethod
    def idle(cls):
        """Create a :class:`Request` to idle."""
        return cls(Type.idle, None)

    @classmethod
    def execute(cls, amount):
        """Create a :class:`Request` to spend some time executing."""
        return cls(Type.execute, amount)

    @classmethod
    def timer(cls, time):
        """Create a :class:`Request` to set a timer for the current context."""
        return cls(Type.timer, time)
