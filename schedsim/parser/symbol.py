#!/usr/bin/env python3
"""Defines the :class:`Symbol`."""

import enum
import re
from .node import Node

# regular expressions to validate symbols
_RE_IDENTIFIER_STR = r'[A-Za-z_][A-Za-z0-9_]*'
_RE_INTEGER_STR = r'[+-]?[0-9]+'
_RE_DECIMAL_STRS = (r'[+-]?[0-9]+\.?[0-9]*', r'[+-]?\.[0-9]+')
_RE_FRACTION_STR = r'[+-]?[0-9]+/[+-]?[0-9]+'

_RE_IDENTIFIER = re.compile(_RE_IDENTIFIER_STR)
_RE_INTEGER = re.compile(_RE_INTEGER_STR)
_RE_DECIMAL = re.compile(rf'(?:{"|".join(_RE_DECIMAL_STRS)})')
_RE_FRACTION = re.compile(_RE_FRACTION_STR)
# note: decimal subsumes integer
_RE_SYMBOL = re.compile(
    rf'(?:{"|".join((_RE_IDENTIFIER_STR, *_RE_DECIMAL_STRS, _RE_FRACTION_STR))})'
)

class SymbolKind(enum.Enum):
    """Types of symbols."""
    Identifier = _RE_IDENTIFIER
    Decimal = _RE_DECIMAL
    Fraction = _RE_FRACTION

class Symbol(Node):
    """A symbol-node.

    The name of the symbol is in :attr:`self.symbol`.
    """

    def __init__(self, cursor, symbol=''):
        """Create a :class:`Symbol`.

        `symbol` specifies the name of the symbol.
        """
        super().__init__(cursor)
        self.symbol = symbol

    def __repr__(self):
        return f'Symbol({self.symbol})'

    def __eq__(self, value):
        if type(value) == Symbol:
            return self.symbol == value.symbol
        return False

    def __add__(self, value):
        return Symbol(self.cursor, self.symbol.__add__(value))

    def __iadd__(self, value):
        #self.symbol.__iadd__(value)
        self.symbol += value
        return self

    def __mul__(self, value):
        return Symbol(self.cursor, self.symbol.__mul__(value))

    def __imul__(self, value):
        #self.symbol.__imul__(value)
        self.symbol *= value
        return self

    def __getitem__(self, key):
        return Symbol(self.cursor, self.symbol.__getitem__(key))

    def __len__(self):
        return self.symbol.__len__()

    def isvalid(self):
        """Checks that the name of this symbol is valid."""
        return _RE_SYMBOL.fullmatch(self.symbol)

    def invalid_indices(self, kind):
        """Return indices of invalid characters for the :class:`SymbolKind <kind>`.

        The indices yielded are relative to the previous one.
        The first index is an absolute index.

        When `None` is yielded then the symbol does not look like belonging to the
        :class:`SymbolKind` at all and no indices will be yielded.
        """
        # we'll remove characters until it looks valid
        fixed = self.symbol

        if not fixed:
            yield None
            return
        if kind == SymbolKind.Identifier and not re.search('[a-zA-Z_]', fixed):
            yield None
            return
        if kind in (SymbolKind.Decimal, SymbolKind.Fraction) and not re.search('[0-9]', fixed):
            yield None
            return
        if kind == SymbolKind.Fraction:
            if '/' not in fixed:
                yield None
                return

            # we need to treat fractions differently
            parts = fixed.split('/')

            start = next((i for i, p in enumerate(parts) if p), len(parts))
            parts = parts[start:]

            if all(not p for p in parts[1:]):
                yield None
                return

            for _ in range(0, start):
                yield 0

            ok_offset = -1
            for idx, part in enumerate(parts):
                if idx > 1:
                    # too many slashes
                    yield ok_offset
                    ok_offset = 0
                else:
                    ok_offset += 1

                if not part:
                    continue

                invalid = self._invalid_indices(part, _RE_INTEGER)
                try:
                    total_idx = 0
                    while True:
                        invalid_idx = next(invalid)
                        total_idx += invalid_idx
                        yield ok_offset + invalid_idx
                        ok_offset = 0
                except StopIteration as fixed:
                    ok_offset += len(fixed.value) - total_idx

            return

        yield from self._invalid_indices(fixed, kind.value)

    @staticmethod
    def _invalid_indices(fixed, regex):
        """Helper function for :meth:`invalid_indices`.

        Yields all indices of characters that can be removed to make the string `fixed`
        conforming to `regex`.
        """
        def match():
            while fixed:
                yield regex.match(fixed)
        match = match()
        partial = next(match)

        try:
            while partial is None:
                yield 0
                fixed = fixed[1:]
                partial = next(match)

            prev_invalid = 0
            while partial.span()[1] != len(fixed):
                # index of non-matching character
                invalid = len(partial.group(0))
                yield invalid - prev_invalid
                fixed = fixed[0:invalid] + fixed[invalid + 1:]
                partial = next(match)
                prev_invalid = invalid
        except StopIteration:
            pass

        return fixed
