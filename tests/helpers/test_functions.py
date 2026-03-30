"""Tests for helpers/functions.py — safe_call argument matching."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from helpers.functions import safe_call


def _add(a, b):
    return a + b


def _greet(name, greeting="hello"):
    return f"{greeting} {name}"


def _variadic_kwargs(a, **kwargs):
    return {"a": a, **kwargs}


def _variadic_args(*args):
    return list(args)


def _both(*args, **kwargs):
    return args, kwargs


class TestSafeCallMatchingArgs:
    def test_exact_args(self):
        assert safe_call(_add, 2, 3) == 5

    def test_exact_kwargs(self):
        assert safe_call(_greet, "world", greeting="hi") == "hi world"


class TestSafeCallExtraKwargs:
    def test_extra_kwargs_dropped(self):
        result = safe_call(_add, 2, 3, extra=99)
        assert result == 5

    def test_unknown_kwargs_dropped_with_default(self):
        result = safe_call(_greet, "alice", unknown="x")
        assert result == "hello alice"


class TestSafeCallVarKwargs:
    def test_extra_kwargs_passed(self):
        result = safe_call(_variadic_kwargs, 1, extra="yes", more=42)
        assert result == {"a": 1, "extra": "yes", "more": 42}


class TestSafeCallExtraPositional:
    def test_extra_positional_truncated(self):
        result = safe_call(_add, 2, 3, 999, 888)
        assert result == 5

    def test_single_arg_function(self):
        def identity(x):
            return x

        assert safe_call(identity, 10, 20, 30) == 10


class TestSafeCallVarArgs:
    def test_all_positional_passed(self):
        result = safe_call(_variadic_args, 1, 2, 3, 4, 5)
        assert result == [1, 2, 3, 4, 5]

    def test_both_var_args_and_kwargs(self):
        args, kwargs = safe_call(_both, 1, 2, x="a")
        assert args == (1, 2)
        assert kwargs == {"x": "a"}


def _keyword_only(a, *, key=None, flag=False):
    return (a, key, flag)


class TestSafeCallKeywordOnly:
    def test_keyword_only_accepted(self):
        result = safe_call(_keyword_only, 1, key="x")
        assert result == (1, "x", False)

    def test_unknown_kwargs_dropped_with_keyword_only(self):
        result = safe_call(_keyword_only, 1, key="x", unknown="y")
        assert result == (1, "x", False)

    def test_keyword_only_defaults(self):
        result = safe_call(_keyword_only, 1)
        assert result == (1, None, False)
