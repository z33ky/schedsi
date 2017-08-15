#!/usr/bin/env python3
"""Defines utility functions to help with interpreting."""

from gmpy2 import mpq as Fraction
from parser import String, Symbol, Tuple
from .error import InterpreterError

class NodeTypeError(InterpreterError):
    """This class represents type-errors occurring while interpreting schedsim expressions."""

    def __init__(self, msg, node):
        """Create a :class:`NodeTypeError`."""
        if type(msg) == type:
            super().__init__(f'Expected {msg.__name__}, got {node}', node)
        else:
            super().__init__(msg, node)

class NodeValueError(InterpreterError):
    """This class represents value-errors occurring while interpreting schedsim expressions."""

    def __init__(self, msg, node):
        """Create a :class:`NodeValueError`."""
        super().__init__(msg, node)

class TupleLengthError(InterpreterError):
    """This class represents an error due to invalid tuple length while interpreting
    schedsim expressions.
    """

    def __init__(self, msg, node):
        """Create a :class:`TupleLengthError`."""
        super().__init__(msg, node)

def check_type(node, tp, msg=None):
    """Check that `node` is of type `tp` or raise an :exc:`NodeTypeError`.

    Returns `node`.
    """
    if type(node) != tp:
        raise NodeTypeError(msg if msg is not None else tp, node)
    return node

def check_tuple_len(tup, *, type_msg=None, len_msg=None, least=None, exact=None):
    """Check that `tup` is a :class:`Tuple` of a certain (minimum) length or raise an
    :exc:`NodeTypeError` or :exc:`TupleLengthError`.

    Either `least` or `exact` must be set.

    If either error gets raised, `type_msg` and `len_msg` can be set to specify their messages.

    Returns the length of `tup`.
    """
    check_type(tup, Tuple, type_msg)
    length = len(tup)
    check = None

    len_msg_prefix = f'Expected tuple with length'

    if least is not None:
        check = length >= least
        if len_msg is None:
            len_msg = f'{len_msg_prefix} >= {least}'
    if exact is not None:
        assert check is None
        check = length == exact
        if len_msg is None:
            len_msg = f'{len_msg_prefix} = {exact}'

    assert check is not None

    if not check:
        raise TupleLengthError(len_msg, tup)

    return length

def set_once(params, key, value, msg=None):
    """Set `params[key]` to `value` if it is not yet set.
    Raise an :exc:`InterpreterError` otherwise.

    `msg` optionally specifies the message for the :exc:`InterpreterError`.
    """
    if key in params.keys():
        raise InterpreterError(msg if msg is not None else f'Parameter {key} already set')
    params[key] = value

def get_value(node, tp):
    """Extract a value from `node`.

    `tp` specifies the type of the value.  It may be one of `bool`, `int`, `float`, `str` or a
    tuple/list thereof. It may be nested. `None` or an empty tuple specifies that anything is
    allowed.

    If the value cannot be parsed from `node`, a :exc:`NodeValueError` is raised.
    """
    if tp in (None, ()):
        tp = ((), bool, float, str)
    elif type(tp) not in (tuple, list):
        tp = (tp,)

    if type(node) == Symbol:
        symbol = node.symbol

        if bool in tp:
            if symbol == 'True':
                return True
            if symbol == 'False':
                return False

        if float in tp or Fraction in tp:
            try:
                value = Fraction(symbol)
                if value.denominator == 1:
                    return int(value.numerator)
                return value
            except ValueError:
                pass
        elif int in tp:
            try:
                return int(symbol)
            except ValueError:
                pass
    elif type(node) == String and str in tp:
        return node.string
    elif type(node) == Tuple:
        tp_tuples = (tup for tup in tp if type(tup) is tuple)
        tp_tuple = next(tp_tuples)
        assert next(tp_tuples, None) is None, "tp for get_value can only have a single tuple"
        return (*(get_value(v, tp_tuple) for v in node),)

    values_str = []
    if bool in tp:
        values_str += ['Symbol(True)', 'Symbol(False)']
    if float in tp:
        values_str += ['Symbol(number)']
    elif int in tp:
        values_str += ['Symbol(integer)']
    if str in tp:
        values_str += ['a String']

    if len(values_str) == 1:
        values_str = values_str[0]
    else:
        values_str = f'{", ".join(values_str[:-1])} or {values_str[-1]}'

    raise NodeValueError(f'Expected {values_str}, got {node}', node)

def get_single_param(tup, tp):
    """Extract a (`key`, `value`)-pair from `tup`.

    `tup` must be a :class:`Tuple` of length 2, otherwise an :exc:`InterpreterError` is raised.

    `tp` specifies the type of `value`.  It may be one of `bool`, `int`, `float`, `str` or a
    tuple/list thereof. See :func:`get_value`.

    If `value` cannot be parsed from the `tup`, an :exc:`InterpreterError` is raised.
    """
    check_tuple_len(tup, exact=2)
    return check_type(tup[0], Symbol).symbol, get_value(tup[1], tp)

def get_params(tup, tp):
    """Extract (`key`, `value`)-pairs from `tup`.

    `tup` must be a :class:`Tuple` containing :class:`Tuple <Tuples>` of length 2,
    otherwise an :exc:`InterpreterError` is raised.

    `tp` specifies the type of `value`.  It may be one of `bool`, `int`, `float`, `str` or a
    tuple/list thereof. See :func:`get_value`.

    If `value` cannot be parsed from the `tup`, an :exc:`InterpreterError` is raised.
    """
    check_type(tup, Tuple)
    params = {}
    for param in tup:
        key, value = get_single_param(param, tp)
        set_once(params, key, value)
    return params

def get_param_keys(tup):
    """Extract (`key`, `value`)-pairs from `tup`.

    `tup` must be a :class:`Tuple` containing :class:`Tuple <Tuples>` of length 2,
    otherwise an :exc:`InterpreterError` is raised.

    `value` will stay a :class:`Node` and needs to be retrieved using :func:`get_value`.
    """
    check_type(tup, Tuple)
    params = {}
    for param in tup:
        check_tuple_len(param, exact=2)
        set_once(params, check_type(param[0], Symbol).symbol, param[1])
    return params
