"""Defines the loggers."""

# this is to import the replay functions
from . import binarylog
from .binarylog import BinaryLog
from .ganttlog import GanttLog
from .graphlog import GraphLog
from .modulegraphlog import ModuleGraphLog
from .multiplexer import Multiplexer
from .textlog import TextLog, Align as TextLogAlign
