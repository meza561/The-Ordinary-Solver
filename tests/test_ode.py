"""
ODE solver tests.

These verify that the RK4 integration in /solve produces numerical results
that match the known analytical solutions for classical equations. If any
of these breaks, the heart of the project is broken.

Tolerance note: RK4 with h=0.01 is roughly 4th-order accurate. We use 1e-3
as the default tolerance, which is generous enough to absorb floating-point
drift over thousands of steps but tight enough to catch real regressions.
"""
import math
import pytest

def _post(client, payload):
    """Helper: POST /solve and return the parsed JSON response."""
    return client.post("/solve", json=payload).get_json()


# ---------------------------------------------------------------------------
# First-order ODEs with known closed-form solutions
# ---------------------------------------------------------------------------

def test_exponential_growth(client):
    """y' = y, y(0) = 1 has the analytical solution y = e^x.
    At x=1, the solution is e ≈ 2.71828."""
    d = _post(client, {
        "mode": "single", "eq1": "y' = y",
        "indep0": 0, "dep1_0": 1, "indep_end": 1,
    })
    assert d["dep1"][-1] == pytest.approx(math.e, abs=1e-3)


def test_separable_equation(client):
    """y' = x/y with y(0) = 1 has solution y = sqrt(x^2 + 1).
    At x=2, y = sqrt(5) ≈ 2.2360."""
    d = _post(client, {
        "mode": "single", "eq1": "y' = x/y",
        "indep0": 0, "dep1_0": 1, "indep_end": 2,
    })
    assert d["dep1"][-1] == pytest.approx(math.sqrt(5), abs=1e-3)


def test_order_auto_detection_first_order(client):
    """A first-order equation should be detected as order 1."""
    d = _post(client, {
        "mode": "single", "eq1": "y' = y",
        "indep0": 0, "dep1_0": 1, "indep_end": 1,
    })
    assert d["order"] == 1


# ---------------------------------------------------------------------------
# Second-order ODEs
# ---------------------------------------------------------------------------

def test_simple_harmonic_oscillator(client):
    """y'' + 4y = 0 with y(0)=1, y'(0)=0 has solution y = cos(2x).
    At x=pi, y = cos(2*pi) = 1."""
    d = _post(client, {
        "mode": "single", "eq1": "y'' + 4y = 0",
        "indep0": 0, "dep1_0": 1, "dep2_0": 0, "indep_end": math.pi,
    })
    assert d["dep1"][-1] == pytest.approx(1.0, abs=1e-3)


def test_hyperbolic_equation(client):
    """y'' - y = 0 with y(0)=1, y'(0)=1 has solution y = e^x.
    At x=1, y = e."""
    d = _post(client, {
        "mode": "single", "eq1": "y'' - y = 0",
        "indep0": 0, "dep1_0": 1, "dep2_0": 1, "indep_end": 1,
    })
    assert d["dep1"][-1] == pytest.approx(math.e, abs=1e-3)


def test_order_auto_detection_second_order(client):
    """y'' + 4y = 0 should be detected as order 2."""
    d = _post(client, {
        "mode": "single", "eq1": "y'' + 4y = 0",
        "indep0": 0, "dep1_0": 1, "dep2_0": 0, "indep_end": 1,
    })
    assert d["order"] == 2


# ---------------------------------------------------------------------------
# 2D systems
# ---------------------------------------------------------------------------

def test_circular_motion_system(client):
    """x' = y, y' = -x starting at (1, 0) traces a unit circle.
    After 2π we should return to (1, 0)."""
    d = _post(client, {
        "mode": "system", "eq1": "y", "eq2": "-x",
        "indep0": 0, "dep1_0": 1, "dep2_0": 0, "indep_end": 2 * math.pi,
    })
    assert d["dep1"][-1] == pytest.approx(1.0, abs=1e-2)
    assert d["dep2"][-1] == pytest.approx(0.0, abs=1e-2)


# ---------------------------------------------------------------------------
# Integration direction
# ---------------------------------------------------------------------------

def test_backward_integration(client):
    """y' = y integrated from x=0 backward to x=-1 should give e^(-1).
    Regression: the original code used abs() and integrated forward
    regardless of direction; this is now fixed with copysign."""
    d = _post(client, {
        "mode": "single", "eq1": "y' = y",
        "indep0": 0, "dep1_0": 1, "indep_end": -1,
    })
    assert d["dep1"][-1] == pytest.approx(1.0 / math.e, abs=1e-3)
    # And the independent variable actually went backward:
    assert d["indep"][-1] < d["indep"][0]


# ---------------------------------------------------------------------------
# Error handling and edge cases
# ---------------------------------------------------------------------------

def test_identical_endpoints_returns_error(client):
    """Start == End should fail cleanly with 400, not divide by zero."""
    r = client.post("/solve", json={
        "mode": "single", "eq1": "y' = y",
        "indep0": 3, "dep1_0": 1, "indep_end": 3,
    })
    assert r.status_code == 400
    assert "identical" in r.get_json()["error"].lower()


def test_step_cap_prevents_hang(client):
    """A huge integration range must terminate via the step cap (200k),
    not loop for billions of iterations."""
    d = _post(client, {
        "mode": "single", "eq1": "y' = 0",
        "indep0": 0, "dep1_0": 1, "indep_end": 1e8,
    })
    # Must come back; must not exceed MAX_STEPS + 1 (initial point).
    assert d["step_count"] <= 200_001


def test_asymptote_blowup_is_truncated(client):
    """y' = y^2 with y(0) = 1 blows up at x = 1. The solver should detect
    the blow-up, mark truncated=True, and not return infinities."""
    d = _post(client, {
        "mode": "single", "eq1": "y' = y^2",
        "indep0": 0, "dep1_0": 1, "indep_end": 2,
    })
    assert d["truncated"] is True
    # The last recorded value must be finite, not inf/nan.
    assert math.isfinite(d["dep1"][-1])


# ---------------------------------------------------------------------------
# Candidate-solution overlay (the f(x) check feature)
# ---------------------------------------------------------------------------

def test_check_overlay_matches_correct_solution(client):
    """When the candidate IS the analytical solution, max error is tiny."""
    d = _post(client, {
        "mode": "single", "eq1": "y'' + 4y = 0",
        "indep0": 0, "dep1_0": 1, "dep2_0": 0, "indep_end": 3,
        "check": "cos(2x)",
    })
    assert d["check"] is not None
    max_err = max(abs(c - s) for c, s in zip(d["check"], d["dep1"]))
    assert max_err < 1e-3


def test_check_overlay_detects_wrong_solution(client):
    """When the candidate is wrong, the error is large enough to notice."""
    d = _post(client, {
        "mode": "single", "eq1": "y' = y",
        "indep0": 0, "dep1_0": 1, "indep_end": 2,
        "check": "x^2",  # not e^x — should differ noticeably
    })
    assert d["check"] is not None
    max_err = max(abs(c - s) for c, s in zip(d["check"], d["dep1"]))
    assert max_err > 0.5