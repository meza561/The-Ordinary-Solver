"""
Reference implementations of the regression fits used in the LSRL and
Nonlinear Fit tabs.

The actual fits run client-side in script.js so the user gets instant
feedback as they edit the data. These Python implementations are NOT
called by the running core — they exist as the authoritative source of
truth for what the algorithms should do, and as the testable version
for our pytest suite.

If the JS and Python ever disagree on the answer to a fit, the Python
is right and the JS has a bug. (Or vice versa, but we have tests on
the Python, so it's harder to be wrong here.)

All non-linear fits below use linearization (least-squares in transformed
space). This is fast, closed-form, and matches what the JS does. A future
upgrade would be true nonlinear least-squares via Levenberg-Marquardt —
that's noted in TODO comments where it would matter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class LinearFit:
    """Result of a least-squares linear fit y = a + b*x."""
    intercept: float   # a
    slope: float       # b
    r: float           # correlation coefficient
    r_squared: float   # coefficient of determination


def parse_pairs(text: str) -> tuple[list[float], list[float]]:
    """Parse a multi-line 'x, y' string into matching lists.

    Each line is one data point. Separator can be comma, space, or tab.
    Lines that don't parse to two numbers are silently skipped, matching
    the JS behavior so a user pasting messy data doesn't get an error
    for stray blank lines or header rows.
    """
    xs: list[float] = []
    ys: list[float] = []
    for line in text.splitlines():
        parts = [p for p in line.replace(",", " ").replace("\t", " ").split()
                 if p]
        if len(parts) < 2:
            continue
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        xs.append(x)
        ys.append(y)
    return xs, ys


def linear_fit(xs: list[float], ys: list[float]) -> LinearFit:
    """Ordinary least-squares fit of y = a + b*x.

    Closed-form via the standard normal equations. Identical to what
    statistics textbooks call LSRL.
    """
    n = len(xs)
    if n < 2:
        raise ValueError("Need at least 2 points for a linear fit.")
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    syy = sum(y * y for y in ys)

    denom = n * sxx - sx * sx
    if denom == 0:
        # All x values are identical — vertical line, slope undefined.
        raise ValueError("All x values are identical; slope is undefined.")
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    r_denom = math.sqrt(denom * (n * syy - sy * sy))
    r = 0.0 if r_denom == 0 else (n * sxy - sx * sy) / r_denom
    return LinearFit(intercept=intercept, slope=slope, r=r, r_squared=r * r)


def r_squared(ys: list[float], preds: list[float]) -> float:
    """R² computed in the ORIGINAL space (not the linearized one).

    For the non-linear fits we linearize to solve in closed form, but we
    must report R² against the original y values — otherwise the metric
    is incomparable across model families.
    """
    n = len(ys)
    if n == 0:
        raise ValueError("Cannot compute R² with no data.")
    y_bar = sum(ys) / n
    ss_tot = sum((y - y_bar) ** 2 for y in ys)
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, preds))
    return 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot


def exponential_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Fit y = a * exp(b * x) via linearization in log-y space.

    Returns (a, b). Requires all y > 0 (you can't take log of nonpositive).

    TODO(future): replace with Levenberg-Marquardt for true nonlinear
    least squares. Linearization weights large y values less than small
    ones in the original space.
    """
    if any(y <= 0 for y in ys):
        raise ValueError("Exponential fit requires all y > 0.")
    log_ys = [math.log(y) for y in ys]
    fit = linear_fit(xs, log_ys)
    return math.exp(fit.intercept), fit.slope


def power_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Fit y = a * x^b via linearization in log-log space.

    Returns (a, b). Requires all x > 0 and all y > 0.
    """
    if any(x <= 0 for x in xs):
        raise ValueError("Power fit requires all x > 0.")
    if any(y <= 0 for y in ys):
        raise ValueError("Power fit requires all y > 0.")
    log_xs = [math.log(x) for x in xs]
    log_ys = [math.log(y) for y in ys]
    fit = linear_fit(log_xs, log_ys)
    return math.exp(fit.intercept), fit.slope


def log_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Fit y = a + b * ln(x). Requires all x > 0.

    Returns (a, b).
    """
    if any(x <= 0 for x in xs):
        raise ValueError("Logarithmic fit requires all x > 0.")
    log_xs = [math.log(x) for x in xs]
    fit = linear_fit(log_xs, ys)
    return fit.intercept, fit.slope


def polynomial_fit(xs: list[float], ys: list[float],
                   degree: int) -> list[float]:
    """Fit y = c0 + c1*x + c2*x² + ... + cN*x^N via the normal equations.

    Returns coefficients [c0, c1, ..., cN]. Requires len(xs) >= degree + 1.

    Uses pure Python matrix algebra; no numpy dependency in this module
    so the reference is dependency-free and easy to audit.
    """
    if degree < 1:
        raise ValueError("Degree must be at least 1.")
    n = len(xs)
    if n < degree + 1:
        raise ValueError(
            f"Need at least {degree + 1} points for degree {degree}."
        )

    # Build Vandermonde-style design matrix X where row i is [1, x_i, x_i², ...]
    X = [[x ** k for k in range(degree + 1)] for x in xs]

    # Normal equations: (X^T X) c = X^T y
    XtX = _matmul(_transpose(X), X)
    Xty = _matvec(_transpose(X), ys)
    return _solve(XtX, Xty)


# --- tiny matrix helpers, intentionally no numpy here ----------------------

def _transpose(M: list[list[float]]) -> list[list[float]]:
    return [list(row) for row in zip(*M)]


def _matmul(A: list[list[float]],
            B: list[list[float]]) -> list[list[float]]:
    return [[sum(A[i][k] * B[k][j] for k in range(len(B)))
             for j in range(len(B[0]))]
            for i in range(len(A))]


def _matvec(A: list[list[float]], v: list[float]) -> list[float]:
    return [sum(A[i][k] * v[k] for k in range(len(v)))
            for i in range(len(A))]


def _solve(A: list[list[float]], b: list[float]) -> list[float]:
    """Solve A x = b by Gauss-Jordan elimination with partial pivoting."""
    n = len(A)
    # Augmented matrix; copy so we don't mutate the caller's data.
    M = [row[:] + [b[i]] for i, row in enumerate(A)]

    for i in range(n):
        # Partial pivot: swap in the row with the largest |value| in column i.
        pivot = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[pivot] = M[pivot], M[i]
        if M[i][i] == 0:
            raise ValueError("Singular matrix; cannot solve.")
        # Eliminate column i from all other rows.
        for r in range(n):
            if r == i:
                continue
            factor = M[r][i] / M[i][i]
            for c in range(i, n + 1):
                M[r][c] -= factor * M[i][c]

    return [M[i][n] / M[i][i] for i in range(n)]


def polynomial_predict(coeffs: list[float], x: float) -> float:
    """Evaluate a polynomial given coefficients [c0, c1, c2, ...]."""
    return sum(c * x ** k for k, c in enumerate(coeffs))