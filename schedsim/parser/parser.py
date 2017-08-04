#!/usr/bin/env python3
"""Parser for schedsim-expressions.

The expressions are documented in `schedsim`.
"""

from .tuple import Tuple
from .string import String
from .symbol import Symbol

class ParserError(RuntimeError):
    """This class is for errors raised by :class:`Parser`."""

    def __init__(self, msg, node=None):
        """Create a :class:`ParserError`."""
        super().__init__(msg, node)
        self.msg = msg
        self.node = node

class Parser:
    """Parse schedsim-DSL to tuples, strings and symbols."""
    _buf = None  # single char buffer for peek()

    def __init__(self, data):
        """Create a :class:`Parser`.

        `data` is the stream from which the DSL is read.
        """
        self._data = data

    def __iter__(self):
        """Iterate over all root :class:`Node <Nodes>`."""
        while True:
            node = self.parse_root()
            if node is None:
                return
            else:
                yield node

    def _getch(self):
        """Read a character."""
        if self._buf is not None:
            ch = self._buf
            self._buf = None
        else:
            ch = self._data.read(1)

        return ch

    def _readline(self):
        """Read to the end of the current line."""
        line = self._data.readline()

        if line[-1:] == '\n':
            line = line[:-1]

        return line

    def _peek(self):
        """Read a character without removing it.

        Multiple consecutive calls return the same character.
        """
        if self._buf is None:
            self._buf = self._data.read(1)
        return self._buf

    def parse_root(self):
        """Parse a root element.

        Must be a tuple.
        """
        while True:
            ch = self._getch()
            if ch == '':
                return None
            elif ch.isspace():
                pass
            elif ch == ';':
                self._readline()
            elif ch == '(':
                return self.parse_tuple()
            else:
                raise ParserError(f'Unexpected character ({ch}, {ord(ch)}) in root')

    def parse_tuple(self):
        """Parse a tuple."""
        tup = Tuple()
        while True:
            ch = self._peek()
            if ch == '':
                raise ParserError('Unexpected EOF while parsing tuple', tup)
            elif ch.isspace():
                self._getch()
            elif ch == ';':
                self._getch()
                self._readline()
            elif ch == '(':
                self._getch()
                tup.append(self.parse_tuple())
            elif ch == ')':
                self._getch()
                return tup
            elif ch == '"':
                self._getch()
                tup.append(self.parse_string())
            else:
                tup.append(self.parse_symbol())

    def parse_string(self):
        """Parse a string."""
        string = String()
        while True:
            ch = self._getch()
            if ch == '':
                raise ParserError('UnexpectedEof while parsing string', string)
            elif ch == '"':
                break
            elif ch == '\n':
                raise ParserError('Missing end-" for string', string)
            else:
                string += ch

        if not string.isvalid():
            raise ParserError('Unprintable character(s) in string', string)

        return string

    def parse_symbol(self):
        """Parse a string."""
        init = self._getch()
        symbol = Symbol(init)
        while True:
            ch = self._peek()
            if ch.isspace() or ch in ('', ')', ';'):
                break
            else:
                symbol += self._getch()

        if not symbol.isvalid():
            raise ParserError('Malformed symbol', symbol)

        return symbol
