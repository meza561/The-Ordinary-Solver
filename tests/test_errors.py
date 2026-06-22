"""
Error-path tests.

Most of app.py's remaining uncovered lines are error-handling branches
in the route handlers — the code that runs when user input is malformed,
when SymPy can't integrate, when the parser chokes. These tests exercise
those paths so the app fails gracefully rather than leaking stack traces.
"""


def test_solve_garbage_equation_returns_400(client):
    """A syntactically broken equation fails cleanly with 400, not 500."""
    r = client.post("/solve", json={
        "mode": "single", "eq1": "this is not math",
        "indep0": 0, "dep1_0": 1, "indep_end": 1,
    })
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_solve_unknown_variable_returns_400(client):
    """Equation referencing a variable not in the ODE context."""
    r = client.post("/solve", json={
        "mode": "single", "eq1": "y' = zebra",
        "indep0": 0, "dep1_0": 1, "indep_end": 1,
    })
    assert r.status_code == 400


def test_solve_non_numeric_initial_condition_returns_400(client):
    """If a user sends 'abc' as x₀, the float() conversion must fail
    gracefully rather than crash the worker."""
    r = client.post("/solve", json={
        "mode": "single", "eq1": "y' = y",
        "indep0": "abc", "dep1_0": 1, "indep_end": 1,
    })
    assert r.status_code == 400


def test_solve_check_with_bad_expression_silently_omits_overlay(client):
    """A broken candidate f(x) must not kill the whole solve. The
    numerical solution still comes back, just without the overlay."""
    d = client.post("/solve", json={
        "mode": "single", "eq1": "y' = y",
        "indep0": 0, "dep1_0": 1, "indep_end": 1,
        "check": "broken \\frac{",
    }).get_json()
    assert "dep1" in d
    assert d["check"] is None


def test_differentiate_empty_expression_handles_gracefully(client):
    """An empty expression either errors with 400 or trivially returns 0.
    Both are defensible; what matters is the route never crashes.
    Investigation revealed the actual behavior is the latter — empty
    string parses to '0', differentiates to 0."""
    r = client.post("/differentiate", json={"expr": ""})
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert r.get_json().get("plain") in ("0", "")

def test_differentiate_unknown_var_returns_400(client):
    """Asking to differentiate wrt a variable we don't support."""
    r = client.post("/differentiate", json={"expr": "x^2", "var": "zebra"})
    assert r.status_code == 400


def test_differentiate_order_caps_at_5(client):
    """Order > 5 should silently clamp to 5, not error."""
    d = client.post("/differentiate",
                    json={"expr": "x^10", "order": 100}).get_json()
    assert "plain" in d
    # 10! / 5! = 30240, so the 5th derivative of x^10 is 30240*x^5
    assert "30240" in d["plain"]


def test_differentiate_order_zero_clamps_to_one(client):
    """Order <= 0 also clamps to 1."""
    d = client.post("/differentiate",
                    json={"expr": "x^3", "order": 0}).get_json()
    assert d["plain"] == "3*x**2"


def test_integrate_unknown_kind_returns_400(client):
    """Typo or unsupported integral type."""
    r = client.post("/integrate", json={"kind": "quintuple", "integrand": "x"})
    assert r.status_code == 400


def test_integrate_garbage_integrand_returns_400(client):
    r = client.post("/integrate", json={
        "kind": "single", "integrand": "&&&",
        "bounds": [["x", "0", "1"]],
    })
    assert r.status_code == 400


def test_index_route_returns_html(client):
    """GET / renders the page successfully — catches template breakage."""
    r = client.get("/")
    assert r.status_code == 200
    assert b"The Ordinary Solver" in r.data


def test_malformed_post_body_does_not_500(client):
    """Garbage POST body should not crash the worker."""
    r = client.post("/solve", data="not json",
                    content_type="application/json")
    assert r.status_code < 500