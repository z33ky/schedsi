#!/usr/bin/env python3
"""Parser for schedsim-expressions.

The expressions are documented in `schedsim`.
"""

from .cursor import Cursor
from .tuple import Tuple
from .string import String
from .symbol import Symbol

class ParserError(RuntimeError):
    """This class is for errors raised by :class:`Parser`."""

    def __init__(self, msg, cursor, node=None):
        """Create a :class:`ParserError`."""
        super().__init__(msg, cursor, node)
        self.msg = msg
        self.cursor = cursor
        self.node = node

    def get_range(self):
        """Return a tuple of cursors marking the begin and end of the node.

        If no node is contained in the error, the tuple will have the two cursors
        pointing to the location where the parser failed.
        """
        cursor = self.node and self.node.cursor
        if cursor and cursor[1]:
            assert cursor[1] == self.cursor
        return cursor and cursor[0] or self.cursor, self.cursor

class UnexpectedEof(ParserError):
    """This class is for errors due to an unexpected EOF."""

    def __init__(self, what, cursor, node):
        """Create a :class:`UnexpectedEof`."""
        super().__init__('Unexpected EOF while parsing ' + what, cursor, node)

class UntermiatedString(ParserError):
    """This class is for errors due to a missing string terminator."""

    def __init__(self, cursor, node):
        """Create a :class:`UntermiatedString`."""
        super().__init__('Missing end-" for string', cursor, node)

class MalformedString(ParserError):
    """This class is for errors due to malformed strings."""

    def __init__(self, cursor, string):
        """Create a :class:`MalformedString`."""
        assert isinstance(string, String)
        super().__init__('Unprintable character(s) in string', cursor, string)

class MalformedSymbol(ParserError):
    """This class is for errors due to malformed symbols."""

    def __init__(self, cursor, symbol):
        """Create a :class:`MalformedSymbol`."""
        assert isinstance(symbol, Symbol)
        super().__init__(f'Malformed symbol "{symbol.symbol}"', cursor, symbol)

class Parser:
    """Parse schedsim-DSL to tuples, strings and symbols."""
    line = 0
    column = 0
    _newline = True
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
        """Read a character.

        Takes care of incrementing :attr:`self.line` and :attr:`self.column`.
        """
        if self._buf is not None:
            ch = self._buf
            self._buf = None
        else:
            ch = self._data.read(1)

        if self._newline:
            self.line += 1
            self.column = 1
            self._newline = False
        elif ch != '':
            self.column += 1

        if ch == '\n':
            self._newline = True

        return ch

    def _readline(self):
        """Read to the end of the current line."""
        line = self._data.readline()

        if line[-1:] == '\n':
            line = line[:-1]

        self.line += 1
        self.column = 0

        return line

    def _peek(self):
        """Read a character without removing it.

        Multiple consecutive calls return the same character.
        """
        if self._buf is None:
            self._buf = self._data.read(1)
        return self._buf

    @property
    def cursor(self):
        """A cursor to where the parser is at."""
        cursor = Cursor(self.line, self.column, self.byte_offset - 1)
        if self._buf is not None:
            cursor.byte -= 1
            cursor.col -= 1
            if cursor.col == 0:
                cursor.line -= 1
                cursor.col = 1
        return cursor

    @property
    def byte_offset(self):
        """The byte offset into the file that the parser is at."""
        return self._data.tell()

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
                raise ParserError(f'Unexpected character ({ch}, {ord(ch)}) in root', self.cursor)

    def parse_tuple(self):
        """Parse a tuple."""
        tup = Tuple(self.cursor)
        while True:
            ch = self._peek()
            if ch == '':
                raise UnexpectedEof('tuple', self.cursor, tup)
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
                tup.set_end(self.cursor)
                return tup
            elif ch == '"':
                self._getch()
                tup.append(self.parse_string())
            else:
                tup.append(self.parse_symbol())

    def parse_string(self):
        """Parse a string."""
        string = String(self.cursor)
        while True:
            ch = self._getch()
            if ch == '':
                raise UnexpectedEof('string', self.cursor, string)
            elif ch == '"':
                break
            elif ch == '\n':
                # 'unread' this character
                cursor = self.cursor
                cursor.col -= 1
                cursor.byte -= 1
                raise UntermiatedString(cursor, string)
            else:
                string += ch

        if not string.isvalid():
            raise MalformedString(self.cursor, string)

        string.set_end(self.cursor)

        return string

    def parse_symbol(self):
        """Parse a string."""
        init = self._getch()
        symbol = Symbol(self.cursor, init)
        while True:
            ch = self._peek()
            if ch.isspace() or ch in ('', '(', ')', ';'):
                break
            else:
                symbol += self._getch()

        if not symbol.isvalid():
            raise MalformedSymbol(self.cursor, symbol)

        end = self.cursor
        end.col += 1  # account for peeking
        symbol.set_end(end)

        return symbol
