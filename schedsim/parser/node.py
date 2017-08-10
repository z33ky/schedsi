#!/usr/bin/env python3
"""Defines the :class:`Node`."""

from .cursor import Cursor

class Node():
    """A node in in the schedsim tree."""

    def __init__(self, cursor):
        """Create a :class:`Node`.

        `cursor` is either a :class:`Cursor` to the beginning of the node,
        or a tuple of two cursors pointing to the beginning and the end of the node.
        """
        if type(cursor) == Cursor:
            self.cursor = (cursor, None)
        else:
            assert len(cursor) == 2 and all(type(c) == Cursor for c in cursor)
            self.cursor = cursor

    def set_end(self, cursor):
        """Set the end of the node."""
        assert self.cursor[1] is None
        self.cursor = (self.cursor[0], cursor)
