"""The tests of ``{% if x is name %}``."""
from __future__ import annotations

import operator
from collections import abc
from numbers import Number
from typing import Any

from .runtime import Undefined
from .utils import pass_environment


def test_odd(value: int) -> bool:
    return value % 2 == 1


def test_even(value: int) -> bool:
    return value % 2 == 0


def test_divisibleby(value: int, num: int) -> bool:
    return value % num == 0


def test_defined(value: Any) -> bool:
    return not isinstance(value, Undefined)


def test_undefined(value: Any) -> bool:
    return isinstance(value, Undefined)


@pass_environment
def test_filter(env, value: str) -> bool:
    return value in env.filters


@pass_environment
def test_test(env, value: str) -> bool:
    return value in env.tests


def test_none(value: Any) -> bool:
    return value is None


def test_boolean(value: Any) -> bool:
    return value is True or value is False


def test_false(value: Any) -> bool:
    return value is False


def test_true(value: Any) -> bool:
    return value is True


def test_integer(value: Any) -> bool:
    return isinstance(value, int) and value is not True and value is not False


def test_float(value: Any) -> bool:
    return isinstance(value, float)


def test_lower(value: str) -> bool:
    return str(value).islower()


def test_upper(value: str) -> bool:
    return str(value).isupper()


def test_string(value: Any) -> bool:
    return isinstance(value, str)


def test_mapping(value: Any) -> bool:
    return isinstance(value, abc.Mapping)


def test_number(value: Any) -> bool:
    return isinstance(value, Number)


def test_sequence(value: Any) -> bool:
    try:
        len(value)
        value.__getitem__
    except Exception:
        return False
    return True


def test_sameas(value: Any, other: Any) -> bool:
    return value is other


def test_iterable(value: Any) -> bool:
    try:
        iter(value)
    except TypeError:
        return False
    return True


def test_escaped(value: Any) -> bool:
    return hasattr(value, "__html__")


def test_in(value: Any, seq) -> bool:
    return value in seq


TESTS = {
    "odd": test_odd, "even": test_even, "divisibleby": test_divisibleby, "defined": test_defined, "undefined": test_undefined,
    "filter": test_filter, "test": test_test, "none": test_none, "boolean": test_boolean, "false": test_false, "true": test_true,
    "integer": test_integer, "float": test_float, "lower": test_lower, "upper": test_upper, "string": test_string,
    "mapping": test_mapping, "number": test_number, "sequence": test_sequence, "iterable": test_iterable, "callable": callable,
    "sameas": test_sameas, "escaped": test_escaped, "in": test_in,
    "==": operator.eq, "eq": operator.eq, "equalto": operator.eq,
    "!=": operator.ne, "ne": operator.ne,
    ">": operator.gt, "gt": operator.gt, "greaterthan": operator.gt,
    ">=": operator.ge, "ge": operator.ge,
    "<": operator.lt, "lt": operator.lt, "lessthan": operator.lt,
    "<=": operator.le, "le": operator.le,
}
