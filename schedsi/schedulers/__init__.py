"""Defines the schedulers and scheduler addons."""

from . import addons
from .cfs import CFS
from .multilevel_feedback_queue import MLFQ
from .round_robin import RoundRobin
from .scheduler import Scheduler as Single
from .shortest_job_first import SJF
