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


def test_exponent_braces():
    r"""x^{2} should become x**(2) — explicit parens preserve precedence."""
    assert parse_expr("x^{2}+1") == "x**(2)+1"


def test_nested_sqrt_with_exponent():
    r"""\sqrt{x^{2}+1} should parse correctly through both rules."""
    assert parse_expr(r"\sqrt{x^{2}+1}") == "sqrt(x**(2)+1)"


def test_backslash_sin_with_left_right():
    r"""\sin\left(x\right) — full MathLive form — should yield sin(x)."""
    assert parse_expr(r"\sin\left(x\right)") == "sin(x)"


def test_nested_fractions():
    r"""\frac{\frac{1}{x}}{y} exercises the iterative innermost-first frac rule."""
    parsed = parse_expr(r"\frac{\frac{1}{x}}{y}")
    assert parsed == "((((1)/(x)))/(y))"


def test_log10_survives_implicit_multiplication():
    """log10( has a digit before a paren but must not become log1*0*(.
    This is the bug we deliberately shielded against."""
    parsed = parse_expr("log10(x)")
    assert "log1*0" not in parsed
    assert "log10(x)" in parsed


def test_implicit_multiplication_paren_paren():
    """)( should become )*( so things like (x+1)(y+1) parse correctly."""
    assert "*" in parse_expr("(x+1)(y+1)")


def test_greek_theta_phi_rho():
    r"""LaTeX Greek letters used in coordinate systems should de-backslash."""
    assert "theta" in parse_expr(r"\sin(\theta)")
    assert "phi" in parse_expr(r"\cos(\phi)")
    assert "rho" in parse_expr(r"\rho^{2}")