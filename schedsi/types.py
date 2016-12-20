#!/usr/bin/env python3
"""Types that are not defined in other modules."""

import typing

if typing.TYPE_CHECKING:
    from schedsi import binarylog, graphlog, textlog


# using a typing.NewType disallows in-place mathematical operators
Time = float

Log = typing.Union['binarylog.BinaryLog', 'graphlog.GraphLog', 'textlog.TextLog']
