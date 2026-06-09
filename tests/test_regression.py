"""
Regression fit tests.

These exercise core/utils/regression.py, the authoritative reference
implementation of the LSRL and nonlinear fits. The actual fits run in
script.js for instant client-side feedback, but the Python here is the
source of truth — if the two ever disagree, this is what's right.
"""
import math

import pytest

from core.utils.regression import (
    LinearFit, parse_pairs, linear_fit, r_squared,
    exponential_fit, power_fit, log_fit,
    polynomial_fit, polynomial_predict,
)


# ---------------------------------------------------------------------------
# Data parsing
# ---------------------------------------------------------------------------

def test_parse_pairs_handles_comma_space_tab():
    """The parser must accept any of comma, space, or tab as the separator."""
    text = "1, 2\n3 4\n5\t6"
    xs, ys = parse_pairs(text)
    assert xs == [1.0, 3.0, 5.0]
    assert ys == [2.0, 4.0, 6.0]


def test_parse_pairs_skips_junk_lines():
    """Lines that aren't parseable should be silently dropped, not crash."""
    text = "1, 2\nheader row\n\n3, 4\nnot,numbers\n5, 6"
    xs, ys = parse_pairs(text)
    assert xs == [1.0, 3.0, 5.0]
    assert ys == [2.0, 4.0, 6.0]


def test_parse_pairs_returns_empty_for_empty_input():
    assert parse_pairs("") == ([], [])


# ---------------------------------------------------------------------------
# Linear fit (LSRL)
# ---------------------------------------------------------------------------

def test_linear_fit_exact_on_perfect_line():
    """y = 2x + 1 — fit must recover slope 2, intercept 1, r² = 1."""
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [1.0, 3.0, 5.0, 7.0, 9.0]
    fit = linear_fit(xs, ys)
    assert fit.slope == pytest.approx(2.0, abs=1e-12)
    assert fit.intercept == pytest.approx(1.0, abs=1e-12)
    assert fit.r_squared == pytest.approx(1.0, abs=1e-12)


def test_linear_fit_returns_dataclass():
    """LinearFit is a dataclass; attribute access should work."""
    fit = linear_fit([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
    assert isinstance(fit, LinearFit)
    assert fit.slope == pytest.approx(2.0)


def test_linear_fit_too_few_points_raises():
    with pytest.raises(ValueError, match="at least 2"):
        linear_fit([1.0], [2.0])


def test_linear_fit_identical_xs_raises():
    """All x equal means infinite slope; we must raise rather than divide by 0."""
    with pytest.raises(ValueError, match="identical"):
        linear_fit([3.0, 3.0, 3.0], [1.0, 2.0, 3.0])


# ---------------------------------------------------------------------------
# r_squared
# ---------------------------------------------------------------------------

def test_r_squared_perfect_prediction():
    ys = [1.0, 2.0, 3.0, 4.0]
    assert r_squared(ys, ys) == pytest.approx(1.0)


def test_r_squared_predicting_the_mean_gives_zero():
    """If your model is just the mean, R² = 0 by definition."""
    ys = [1.0, 2.0, 3.0, 4.0, 5.0]
    mean = sum(ys) / len(ys)
    preds = [mean] * len(ys)
    assert r_squared(ys, preds) == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Exponential fit
# ---------------------------------------------------------------------------

def test_exponential_fit_recovers_known_parameters():
    """y = 3 * e^(0.5x) — the linearization should recover (3, 0.5) exactly."""
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [3.0 * math.exp(0.5 * x) for x in xs]
    a, b = exponential_fit(xs, ys)
    assert a == pytest.approx(3.0, abs=1e-10)
    assert b == pytest.approx(0.5, abs=1e-10)


def test_exponential_fit_rejects_nonpositive_y():
    with pytest.raises(ValueError, match="y > 0"):
        exponential_fit([1.0, 2.0], [1.0, -1.0])


# ---------------------------------------------------------------------------
# Power fit
# ---------------------------------------------------------------------------

def test_power_fit_recovers_known_parameters():
    """y = 2 * x^1.5 — log-log fit should recover (2, 1.5) exactly."""
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0 * x ** 1.5 for x in xs]
    a, b = power_fit(xs, ys)
    assert a == pytest.approx(2.0, abs=1e-10)
    assert b == pytest.approx(1.5, abs=1e-10)


def test_power_fit_rejects_nonpositive_x():
    with pytest.raises(ValueError, match="x > 0"):
        power_fit([0.0, 1.0], [1.0, 2.0])


# ---------------------------------------------------------------------------
# Log fit
# ---------------------------------------------------------------------------

def test_log_fit_recovers_known_parameters():
    """y = 1 + 2 * ln(x) — linearization in ln-x should give (1, 2)."""
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [1.0 + 2.0 * math.log(x) for x in xs]
    a, b = log_fit(xs, ys)
    assert a == pytest.approx(1.0, abs=1e-10)
    assert b == pytest.approx(2.0, abs=1e-10)


def test_log_fit_rejects_nonpositive_x():
    with pytest.raises(ValueError, match="x > 0"):
        log_fit([0.0, 1.0], [1.0, 2.0])


# ---------------------------------------------------------------------------
# Polynomial fit
# ---------------------------------------------------------------------------

def test_polynomial_quadratic_recovers_known_curve():
    """y = x² should give coeffs [0, 0, 1] (c0 + c1 x + c2 x²)."""
    xs = [-2.0, -1.0, 0.0, 1.0, 2.0]
    ys = [x * x for x in xs]
    coeffs = polynomial_fit(xs, ys, degree=2)
    assert coeffs[0] == pytest.approx(0.0, abs=1e-10)
    assert coeffs[1] == pytest.approx(0.0, abs=1e-10)
    assert coeffs[2] == pytest.approx(1.0, abs=1e-10)


def test_polynomial_cubic_recovers_known_curve():
    """y = 2x³ - x + 5 should give coeffs [5, -1, 0, 2]."""
    def f(x): return 2 * x ** 3 - x + 5
    xs = [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0]
    ys = [f(x) for x in xs]
    coeffs = polynomial_fit(xs, ys, degree=3)
    assert coeffs[0] == pytest.approx(5.0, abs=1e-9)
    assert coeffs[1] == pytest.approx(-1.0, abs=1e-9)
    assert coeffs[2] == pytest.approx(0.0, abs=1e-9)
    assert coeffs[3] == pytest.approx(2.0, abs=1e-9)


def test_polynomial_predict_evaluates_correctly():
    """polynomial_predict([5, -1, 0, 2], 2) = 5 - 2 + 0 + 16 = 19."""
    assert polynomial_predict([5.0, -1.0, 0.0, 2.0], 2.0) == pytest.approx(19.0)


def test_polynomial_too_few_points_raises():
    """Need at least degree+1 points for a degree-N fit."""
    with pytest.raises(ValueError, match="at least"):
        polynomial_fit([1.0, 2.0], [1.0, 4.0], degree=3)