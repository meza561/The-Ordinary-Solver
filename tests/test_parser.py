"""
Parser tests for app.parse_expr.

These verify that LaTeX from MathLive (and plain text) is converted to a
Python-friendly expression string correctly. The two ydy/yddy tests are
genuine regression tests: those were real bugs we shipped fixes for.
"""
from app import parse_expr


def test_empty_string_returns_zero():
    """An empty equation should parse to the literal '0', not blow up."""
    assert parse_expr("") == "0"


def test_simple_frac():
    r"""\frac{x}{y} should become ((x)/(y))."""
    assert parse_expr(r"\frac{x}{y}") == "((x)/(y))"


def test_implicit_multiplication_digit_letter():
    """3y must become 3*y so the AST validator accepts it as arithmetic."""
    assert "3*y" in parse_expr("3y")


def test_y_prime_does_not_become_ydy():
    r"""Regression: MathLive emits y^{\prime} for y'. The old parser replaced
    only the superscript and produced 'ydy', which the validator rejected as
    an unknown symbol. The fix normalizes primes first, then collapses y'."""
    parsed = parse_expr(r"y^{\prime}")
    assert "ydy" not in parsed
    assert parsed == "dy"


def test_y_double_prime_does_not_become_yddy():
    r"""Regression: same bug as above but for second-order derivatives."""
    parsed = parse_expr(r"y^{\prime\prime}")
    assert "yddy" not in parsed
    assert parsed == "ddy"