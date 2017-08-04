#!/usr/bin/env python3
"""Defines the :class:`String`."""

from .node import Node

class String(Node):
    """A string-node.

    The contained string is in :attr:`self.string`.
    """

    def __init__(self, string=''):
        """Create a :class:`String`.

        `string` specifies the contents of the string.
        """
        super().__init__()
        self.string = string

    def __repr__(self):
        return f'String("{self.string}")'

    def __eq__(self, value):
        if type(value) == str:
            return self.string == value
        elif type(value) == String:
            return self.string == value.string
        return False

    def __add__(self, value):
        return String(self.string.__add__(value))

    def __iadd__(self, value):
        #self.string.__iadd__(value)
        self.string += value
        return self

    def __mul__(self, value):
        return String(self.string.__mul__(value))

    def __imul__(self, value):
        #self.string.__imul__(value)
        self.string *= value
        return self

    def __getitem__(self, key):
        return String(self.string.__getitem__(key))

    def __len__(self):
        return self.string.__len__()

    def isvalid(self):
        """Check whether the :class:`String`'s contents are well formed."""
        return all(ch.isprintable() or ch == "" for ch in self.string)
