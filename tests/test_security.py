"""
Security tests for the AST whitelist validator.

The point of these tests: every known way to escape a Python "sandbox" should
be blocked by validate_and_compile. If any of these tests fails, the sandbox
has a hole and the deployed app is potentially exploitable.

Empty __builtins__ alone is NOT a sandbox — Python's attribute access lets you
walk from any object to dangerous classes (the classic ().__class__.__bases__
trick). The validator closes that route by rejecting Attribute nodes outright,
plus comprehensions, lambdas, string constants, and unknown names.
"""
import pytest
from app import validate_and_compile, parse_expr


def _try(expr):
    """Helper: returns True if validation accepts the expression."""
    try:
        validate_and_compile(parse_expr(expr))
        return True
    except (ValueError, SyntaxError):
        return False


# ---------------------------------------------------------------------------
# Attacks that MUST be blocked
# ---------------------------------------------------------------------------

def test_blocks_class_attribute_escape():
    """The classic Python sandbox escape — walk from a literal to its class."""
    assert not _try("().__class__")


def test_blocks_subclasses_chain():
    """The full escape sequence used in real-world exploits."""
    assert not _try("().__class__.__bases__[0].__subclasses__()")


def test_blocks_dunder_on_variable():
    """Even via a normally-allowed name, attribute access is forbidden."""
    assert not _try("x.__class__")


def test_blocks_import():
    """__import__ would be the simplest way to reach os, subprocess, etc."""
    assert not _try("__import__('os')")


def test_blocks_lambda():
    """Lambdas could define unrestricted functions inside the expression."""
    assert not _try("lambda x: x")


def test_blocks_list_comprehension():
    """Comprehensions are full Python and must not pass the whitelist."""
    assert not _try("[i for i in range(3)]")


def test_blocks_string_constants():
    """Only numeric constants are allowed — strings could feed dangerous APIs."""
    assert not _try("'hello'")


def test_blocks_unknown_variable():
    """A variable not in the allowed set must be rejected with a clear error."""
    with pytest.raises(ValueError, match="unknown symbol"):
        validate_and_compile(parse_expr("zebra + 1"))


def test_blocks_call_to_non_whitelisted_function():
    """Even known builtins like print can't be invoked from user input."""
    assert not _try("print(1)")


# ---------------------------------------------------------------------------
# Legitimate expressions that MUST still work
# ---------------------------------------------------------------------------

def test_allows_arithmetic():
    assert _try("2 + 3 * 4")


def test_allows_math_functions():
    assert _try("sin(x) + cos(y)")


def test_allows_constants():
    assert _try("pi * e")