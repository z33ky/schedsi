"""Defines the loggers."""

# this is to import the replay functions
from . import binarylog
from .binarylog import BinaryLog
from .graphlog import GraphLog
from .textlog import TextLog, Align as TextLogAlign
