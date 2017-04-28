#!/usr/bin/env python3
"""Defines a :class:`Time` type."""

import numbers
from gmpy2 import mpq as Time

TimeType = numbers.Rational.register(type(Time(0)))
