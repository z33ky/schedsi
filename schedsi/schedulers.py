#!/usr/bin/env python3
"""Imports all schedulers in one module."""

from schedsi import (multilevel_feedback_queue, penalty_multilevel_feedback_queue,
                     round_robin, shortest_job_first)

SJF = shortest_job_first.SJF
RoundRobin = round_robin.RoundRobin
MLFQ = multilevel_feedback_queue.MLFQ
PMLFQ = penalty_multilevel_feedback_queue.PenaltyMLFQ
