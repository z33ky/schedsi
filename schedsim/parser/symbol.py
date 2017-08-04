#!/usr/bin/env python3
"""Defines the :class:`Symbol`."""

import re
from .node import Node

# regular expression to validate symbols
_RE_SYMBOL = re.compile(r'(?:'
    # identifier
    r'[A-Za-z_][A-Za-z0-9_]*|'
    # decimal
    r'[+-]?[0-9]+\.?[0-9]*|'
    r'[+-]?\.[0-9]+|'
    # fraction
    r'[+-]?[0-9]+/[+-]?[0-9]+'
r')')

class Symbol(Node):
    """A symbol-node.

    The name of the symbol is in :attr:`self.symbol`.
    """

    def __init__(self, symbol=''):
        """Create a :class:`Symbol`.

        `symbol` specifies the name of the symbol.
        """
        super().__init__()
        self.symbol = symbol

    def __repr__(self):
        return f'Symbol({self.symbol})'

    def __eq__(self, value):
        if type(value) == Symbol:
            return self.symbol == value.symbol
        return False

    def __add__(self, value):
        return Symbol(self.symbol.__add__(value))

    def __iadd__(self, value):
        #self.symbol.__iadd__(value)
        self.symbol += value
        return self

    def __mul__(self, value):
        return Symbol(self.symbol.__mul__(value))

    def __imul__(self, value):
        #self.symbol.__imul__(value)
        self.symbol *= value
        return self

    def __getitem__(self, key):
        return Symbol(self.symbol.__getitem__(key))

    def __len__(self):
        return self.symbol.__len__()

    def isvalid(self):
        """Checks that the name of this symbol is valid."""
        return _RE_SYMBOL.fullmatch(self.symbol)
