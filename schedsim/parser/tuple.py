#!/usr/bin/env python3
"""Defines the :class:`Tuple`."""

from .node import Node

class Tuple(Node):
    """A tuple-node with multiple sub-nodes."""

    def __init__(self, cursor, nodes=None):
        """Create a :class:`Tuple`.

        `nodes` is a `list` of :class:`Node`.
        """
        super().__init__(cursor)
        self._nodes = nodes if nodes is not None else []
        assert isinstance(self._nodes, list)
        assert all(isinstance(n, Node) for n in self._nodes)

    def append(self, node):
        """Append a :class:`Node` to the :class:`Tuple`."""
        assert isinstance(node, Node)
        self._nodes.append(node)

    def __str__(self):
        return f'Tuple({"..." if len(self) > 1 else ""})'

    def __repr__(self):
        return f'Tuple({", ".join(repr(n) for n in self._nodes)})'

    def __getitem__(self, key):
        item = self._nodes.__getitem__(key)
        if type(key) == slice:
            if item:
                item = Tuple((item[0].cursor[0], item[-1].cursor[1]), item)
            else:
                item = Tuple((self.cursor[1], self.cursor[1]))
        return item

    def __len__(self):
        return self._nodes.__len__()