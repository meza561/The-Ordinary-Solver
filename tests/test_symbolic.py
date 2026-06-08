"""
Symbolic differentiation and integration tests.

These hit the /differentiate and /integrate endpoints powered by SymPy and
verify both the symbolic step (closed form is correct) and the numeric
fallback (Integral.evalf produces correct numbers when no closed form exists).

We compare on the `plain` field where the output is unambiguous; for results
that depend on SymPy's particular formatting we check substring presence
or use the `numeric` field with pytest.approx.
"""
import math

import pytest


def _diff(client, payload):
    return client.post("/differentiate", json=payload).get_json()


def _int(client, payload):
    return client.post("/integrate", json=payload).get_json()


# ---------------------------------------------------------------------------
# Differentiation
# ---------------------------------------------------------------------------

def test_chain_rule_sin_x_squared(client):
    """d/dx sin(x^2) = 2x*cos(x^2)."""
    d = _diff(client, {"expr": "sin(x^2)"})
    assert d["plain"] == "2*x*cos(x**2)"


def test_product_rule(client):
    """d/dx (x * cos(x)) = -x*sin(x) + cos(x)."""
    d = _diff(client, {"expr": "x*cos(x)"})
    assert "cos(x)" in d["plain"]
    assert "sin(x)" in d["plain"]


def test_partial_derivative(client):
    """Partial wrt y of x^2 * y^3 should be 3*x^2*y^2 (no x or constant terms)."""
    d = _diff(client, {"expr": "x^2 * y^3", "var": "y"})
    assert d["plain"] == "3*x**2*y**2"


def test_higher_order_derivative(client):
    """d²/dx² of x^3 = 6x."""
    d = _diff(client, {"expr": "x^3", "order": 2})
    assert d["plain"] == "6*x"


def test_variables_list_returned(client):
    """The response should report all free symbols so the UI can populate
    the variable selector after the first click."""
    d = _diff(client, {"expr": "x*y + x*z"})
    assert set(d["variables"]) >= {"x", "y", "z"}


def test_differentiate_rejects_unsafe_input(client):
    """Sandbox still holds on the symbolic endpoint."""
    r = client.post("/differentiate", json={"expr": "__import__('os')"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Single integrals
# ---------------------------------------------------------------------------

def test_indefinite_single_integral(client):
    """∫x^2 dx = x^3 / 3."""
    d = _int(client, {"kind": "single", "integrand": "x^2", "var": "x"})
    assert d["plain"] == "x**3/3"


def test_definite_single_integral_sin(client):
    """∫_0^π sin(x) dx = 2."""
    d = _int(client, {
        "kind": "single", "integrand": "sin(x)",
        "bounds": [["x", "0", "pi"]],
    })
    assert d["numeric"] == pytest.approx(2.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Double integrals with coordinate systems
# ---------------------------------------------------------------------------

def test_double_cartesian(client):
    """∫∫ xy over [0,1]×[0,2] = 1."""
    d = _int(client, {
        "kind": "double", "coords": "cartesian", "integrand": "x*y",
        "bounds": [["x", "0", "1"], ["y", "0", "2"]],
    })
    assert d["numeric"] == pytest.approx(1.0, abs=1e-9)


def test_polar_area_of_unit_disk(client):
    """∫∫ 1·r dr dθ over r:[0,1], θ:[0,2π] = π (area of the unit disk).
    Verifies the Jacobian (r) is applied automatically."""
    d = _int(client, {
        "kind": "double", "coords": "polar", "integrand": "1",
        "bounds": [["r", "0", "1"], ["theta", "0", "2*pi"]],
    })
    assert d["numeric"] == pytest.approx(math.pi, abs=1e-9)


# ---------------------------------------------------------------------------
# Triple integrals
# ---------------------------------------------------------------------------

def test_spherical_unit_ball_volume(client):
    """Volume of the unit ball = 4π/3.
    Verifies ρ² sin(φ) Jacobian is applied automatically."""
    d = _int(client, {
        "kind": "triple", "coords": "spherical", "integrand": "1",
        "bounds": [["rho", "0", "1"], ["theta", "0", "2*pi"], ["phi", "0", "pi"]],
    })
    assert d["numeric"] == pytest.approx(4 * math.pi / 3, abs=1e-9)


def test_cylindrical_volume(client):
    """Cylinder r∈[0,1], θ∈[0,2π], z∈[0,2] has volume 2π.
    Verifies the r Jacobian for cylindrical coordinates."""
    d = _int(client, {
        "kind": "triple", "coords": "cylindrical", "integrand": "1",
        "bounds": [["r", "0", "1"], ["theta", "0", "2*pi"], ["z", "0", "2"]],
    })
    assert d["numeric"] == pytest.approx(2 * math.pi, abs=1e-9)


# ---------------------------------------------------------------------------
# Line integrals
# ---------------------------------------------------------------------------

def test_line_scalar_arc_length_of_unit_circle(client):
    """∫ 1 ds around the unit circle = 2π (the circumference)."""
    d = _int(client, {
        "kind": "line", "line_mode": "scalar", "integrand": "1",
        "cx": "cos(t)", "cy": "sin(t)",
        "bounds": [["t", "0", "2*pi"]],
    })
    assert d["numeric"] == pytest.approx(2 * math.pi, abs=1e-9)


def test_line_vector_work_around_unit_circle(client):
    """∫ F·dr where F = (-y, x) around the unit circle = 2π."""
    d = _int(client, {
        "kind": "line", "line_mode": "vector",
        "P": "-y", "Q": "x",
        "cx": "cos(t)", "cy": "sin(t)",
        "bounds": [["t", "0", "2*pi"]],
    })
    assert d["numeric"] == pytest.approx(2 * math.pi, abs=1e-9)


# ---------------------------------------------------------------------------
# Flux integrals
# ---------------------------------------------------------------------------

def test_flux_2d_outward_through_unit_circle(client):
    """Flux of F = (x, y) outward through unit circle = 2π.
    By divergence: ∫∫ ∇·F dA = ∫∫ 2 dA = 2π."""
    d = _int(client, {
        "kind": "flux2d",
        "P": "x", "Q": "y",
        "cx": "cos(t)", "cy": "sin(t)",
        "bounds": [["t", "0", "2*pi"]],
    })
    assert d["numeric"] == pytest.approx(2 * math.pi, abs=1e-9)


def test_flux_3d_through_unit_disk(client):
    """Flux of F = (0, 0, 1) through the unit disk in the z=0 plane = π
    (just the area of the disk, since F is perpendicular and unit)."""
    d = _int(client, {
        "kind": "flux3d",
        "P": "0", "Q": "0", "R": "1",
        "sx": "u*cos(v)", "sy": "u*sin(v)", "sz": "0",
        "bounds": [["u", "0", "1"], ["v", "0", "2*pi"]],
    })
    assert d["numeric"] == pytest.approx(math.pi, abs=1e-9)


# ---------------------------------------------------------------------------
# Numeric fallback for non-elementary integrals
# ---------------------------------------------------------------------------

def test_numeric_fallback_for_gaussian(client):
    """∫_0^2 e^(-x^2) dx has no elementary antiderivative.
    SymPy returns it as sqrt(pi)/2 * erf(2); numerically ≈ 0.882081."""
    d = _int(client, {
        "kind": "single", "integrand": "e^(-x^2)",
        "bounds": [["x", "0", "2"]],
    })
    # The numeric value is what matters here.
    assert d["numeric"] == pytest.approx(0.8820813907624217, abs=1e-9)


# ---------------------------------------------------------------------------
# Security on the symbolic endpoint
# ---------------------------------------------------------------------------

def test_integrate_rejects_unsafe_input(client):
    """The /integrate endpoint also runs through the AST validator."""
    r = client.post("/integrate", json={
        "kind": "single",
        "integrand": "().__class__",
        "bounds": [["x", "0", "1"]],
    })
    assert r.status_code == 400