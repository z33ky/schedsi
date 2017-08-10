#!/usr/bin/env python3
"""Defines the :class:`Cursor`."""

class Cursor:
    """A :class:`Cursor` specifies a location in a file."""

    def __init__(self, *args):
        """Crease a :class:`Cursor`.

        A :class:`Cursor` can be created from (line, column, byte offset)
        or it can copy another :class:`Cursor`.

        An "invalid" cursor can be created from `None`.
        """
        if len(args) == 1:
            arg = args[0]
            if arg is None:
                self.line = self.col = self.byte = None
            elif type(arg) == Cursor:
                self.line = arg.line
                self.col = arg.col
                self.byte = arg.byte
            else:
                raise TypeError()
        elif len(args) == 3:
            self.line, self.col, self.byte = args
        else:
            raise TypeError()

    def __eq__(self, value):
        return type(value) == Cursor and self.__dict__ == value.__dict__

    def get_line_begin(self):
        """Return a :class:`Cursor` pointing to the beginning of the line."""
        return Cursor(self.line, 1, self.byte - self.col + 1)
