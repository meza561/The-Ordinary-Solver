"""
The Ordinary Solver — backend.

Only the ODE solver needs the server (numerical RK4 integration).
The scientific calculator, 2D grapher and 3D surface tabs run entirely
client-side with math.js + Plotly, so they are not handled here.

Security notes
--------------
User-supplied expressions are evaluated with eval(), but inside a locked-down
namespace: __builtins__ is emptied and only a curated set of numpy functions /
constants is exposed. There is no access to imports, file I/O, or process
control, so a malicious expression cannot reach the host. We still cap the
number of integration steps to prevent a single request from hanging a worker.
"""

import ast
import math
import os
import re
from auth import db, login_manager

import numpy as np
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
login_manager.init_app(app)

from auth_routes import auth_bp
app.register_blueprint(auth_bp)

with app.app_context():
    db.create_all()
# ----------------------------------------------------------------------------
# Safe evaluation environment
# ----------------------------------------------------------------------------
# Curated names only. Everything is a numpy ufunc so the same expression can be
# evaluated on a scalar (RK4 inner loop) or a whole array (closed-form overlay).
SAFE_NAMES = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "sqrt": np.sqrt, "cbrt": np.cbrt, "exp": np.exp,
    "log": np.log, "ln": np.log, "log10": np.log10, "log2": np.log2,
    "abs": np.abs, "sign": np.sign, "floor": np.floor, "ceil": np.ceil,
    "pi": np.pi, "e": np.e, "tau": 2 * np.pi,
}

# Empty builtins => no __import__, open, eval, etc. reachable from user input.
EVAL_GLOBALS = {"__builtins__": {}, **SAFE_NAMES}

# Variables the expressions are allowed to reference, by context.
ALLOWED_VARS = {"x", "y", "t", "dy", "ddy"}
ALLOWED_NAMES = set(SAFE_NAMES) | ALLOWED_VARS

# Empty builtins is NOT a sandbox on its own: attribute access (e.g.
# ().__class__.__bases__...) can reach arbitrary objects. So before evaluating
# we walk the AST and allow ONLY arithmetic over whitelisted names/functions.
ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
    ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.USub, ast.UAdd,
)


def validate_and_compile(expr, extra_vars=None):
    """Parse, whitelist-check, and compile an expression. Raises ValueError.

    extra_vars: optional set of additional variable names to allow (used by the
    symbolic differentiator/integrator, which work in x,y,z,r,theta,... ).
    """
    allowed = ALLOWED_NAMES | set(extra_vars) if extra_vars else ALLOWED_NAMES
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            raise ValueError("attribute access is not allowed")
        if isinstance(node, ast.Name):
            if node.id.startswith("_") or node.id not in allowed:
                raise ValueError(f"unknown symbol: {node.id}")
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError("only numeric constants are allowed")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_NAMES:
                raise ValueError("only built-in math functions may be called")
        elif not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
    return compile(tree, "<expr>", "eval")


# Symbolic (SymPy) layer for the Derivative and Integral tabs.
import sympy as sp

# Variables the symbolic tabs understand. Greek names match what parse_expr emits.
SYM_VAR_NAMES = ["x", "y", "z", "r", "theta", "phi", "rho", "t", "u", "v"]
SYM_VARS = {n: sp.Symbol(n, real=True) for n in SYM_VAR_NAMES}

# Map our function names onto SymPy callables/constants.
SYMPY_LOCALS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "arcsin": sp.asin, "arccos": sp.acos, "arctan": sp.atan,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "sqrt": sp.sqrt, "cbrt": sp.cbrt, "exp": sp.exp,
    "log": sp.log, "ln": sp.log,
    "log10": lambda a: sp.log(a, 10), "log2": lambda a: sp.log(a, 2),
    "abs": sp.Abs, "sign": sp.sign, "floor": sp.floor, "ceil": sp.ceiling,
    "pi": sp.pi, "e": sp.E, "tau": 2 * sp.pi,
    **SYM_VARS,
}


def to_sympy(latex_or_text):
    """parse_expr -> AST-validate (safety) -> SymPy expression."""
    parsed = parse_expr(latex_or_text)
    validate_and_compile(parsed, extra_vars=SYM_VAR_NAMES)  # reject anything unsafe
    return sp.sympify(parsed, locals=SYMPY_LOCALS, evaluate=True)


H = 0.01            # fixed RK4 step magnitude
MAX_STEPS = 200_000  # hard cap so an enormous range can't hang the worker


# ----------------------------------------------------------------------------
# LaTeX (MathLive) -> Python expression
# ----------------------------------------------------------------------------
def parse_expr(expr):
    """Convert the LaTeX MathLive emits into a plain Python/numpy expression."""
    if not expr:
        return "0"
    s = expr

    # Derivative notation. Normalize every prime form to literal apostrophes
    # FIRST, then collapse y'' / y' as whole tokens. The old code replaced only
    # the "^{\prime}" superscript, leaving the leading y behind -> "ydy".
    s = s.replace("^{\\prime\\prime}", "''").replace("^{\\prime}", "'")
    s = s.replace("\\prime", "'")
    s = s.replace("\\frac{dy}{dx}", "y'").replace("dy/dx", "y'")
    s = s.replace("y''", "ddy").replace("y'", "dy")
    s = s.replace("''", "ddy").replace("'", "dy")  # bare primes, just in case

    # Exponents with braces first: x^{2} -> x**(2)  (so fracs below see no braces)
    s = re.sub(r"\^\{([^{}]*)\}", r"**(\1)", s)

    # \sqrt{...} -> sqrt(...)  (innermost first via loop)
    sqrt_re = re.compile(r"\\sqrt\{([^{}]*)\}")
    while sqrt_re.search(s):
        s = sqrt_re.sub(r"sqrt(\1)", s)

    # \frac{a}{b} -> ((a)/(b))  (innermost first handles nesting)
    frac_re = re.compile(r"\\frac\{([^{}]*)\}\{([^{}]*)\}")
    while frac_re.search(s):
        s = frac_re.sub(r"((\1)/(\2))", s)

    # Remaining caret -> power
    s = s.replace("^", "**")

    # Structural LaTeX
    s = (s.replace("\\left(", "(").replace("\\right)", ")")
          .replace("\\left[", "(").replace("\\right]", ")")
          .replace("\\left|", "abs(").replace("\\right|", ")")
          .replace("\\cdot", "*").replace("\\times", "*")
          .replace("\\pi", "pi").replace("\\mathrm", "")
          .replace("\\theta", "theta").replace("\\phi", "phi")
          .replace("\\varphi", "phi").replace("\\rho", "rho")
          .replace("\\,", " ").replace("\\!", ""))

    # De-backslash LaTeX function commands: \sin -> sin, \ln -> ln, etc.
    # Longer names first so \arcsin isn't shortened to \arc + sin.
    for fn in ("arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
               "sin", "cos", "tan", "log10", "log2", "log", "ln",
               "exp", "sqrt", "abs", "sign", "floor", "ceil", "cbrt"):
        s = s.replace("\\" + fn, fn)

    # Any leftover braces become parentheses as a safe fallback.
    s = s.replace("{", "(").replace("}", ")")

    # Implicit multiplication: 3y -> 3*y, 2(x+1) -> 2*(x+1), )( -> )*(, )x -> )*x.
    # Shield the only digit-bearing function names so e.g. log10( isn't mangled.
    s = s.replace("log10", "LOGTEN").replace("log2", "LOGTWO")
    s = re.sub(r"(\d)([A-Za-z(])", r"\1*\2", s)   # digit before name/paren
    s = re.sub(r"(\))([A-Za-z0-9(])", r"\1*\2", s)  # paren before name/digit/paren
    s = s.replace("LOGTEN", "log10").replace("LOGTWO", "log2")

    return s.strip() or "0"


def make_callable(expr, mode):
    """Compile a parsed expression into a scalar function f(indep, dep1, dep2)."""
    code = validate_and_compile(expr)

    def get_locals(indep, d1, d2):
        # 1st / 2nd order use x, y (and dy = y'). Systems use t, x, y.
        if mode == "system":
            return {"t": indep, "x": d1, "y": d2}
        return {"x": indep, "y": d1, "dy": d2, "t": indep}

    def fn(indep, d1, d2):
        return eval(code, EVAL_GLOBALS, get_locals(indep, d1, d2))

    return fn


def build_single(eq_raw):
    """Turn a free-form ODE string into (order, F_code) where F(...) == 0.

    Accepts forms like:
        y'' + 3*y' + 4*y = 0     (full equation, '=' allowed)
        y' = x/y                 (solved form)
        x/y                      (legacy: implicitly y' = ...)
    Internally y' -> dy, y'' -> ddy. The order is whichever highest
    derivative appears. The expression must be linear in that highest
    derivative (true for essentially all textbook ODEs); make_single_callable
    isolates it numerically.
    """
    raw = eq_raw or ""
    if "=" in raw:
        lhs, rhs = raw.split("=", 1)
        expr = f"({parse_expr(lhs)}) - ({parse_expr(rhs)})"
    else:
        p = parse_expr(raw)
        # No '=': if a derivative is present treat as "expr = 0",
        # otherwise treat the input as the right-hand side of y' = ...
        expr = p if ("ddy" in p or "dy" in p) else f"dy - ({p})"

    order = 2 if "ddy" in expr else 1
    code = validate_and_compile(expr)
    return order, code


def make_single_callable(code, order):
    """Return (f1, f2) for RK4, isolating the highest derivative from F == 0.

    F is linear in the highest derivative D, so F(D=1) - F(D=0) is its
    coefficient and D = -F(0) / coefficient.
    """
    if order == 1:
        def f1(indep, y, _):
            base = {"x": indep, "y": y, "t": indep}
            f0 = eval(code, EVAL_GLOBALS, {**base, "dy": 0.0})
            f1v = eval(code, EVAL_GLOBALS, {**base, "dy": 1.0})
            coef = f1v - f0
            if coef == 0:
                raise ZeroDivisionError("equation is not solvable for y'")
            return -f0 / coef

        def f2(indep, y, dy):
            return 0.0
    else:  # order 2: state = (y, y'); solve for y''
        def f1(indep, y, dy):
            return dy

        def f2(indep, y, dy):
            base = {"x": indep, "y": y, "dy": dy, "t": indep}
            f0 = eval(code, EVAL_GLOBALS, {**base, "ddy": 0.0})
            f1v = eval(code, EVAL_GLOBALS, {**base, "ddy": 1.0})
            coef = f1v - f0
            if coef == 0:
                raise ZeroDivisionError("equation is not solvable for y''")
            return -f0 / coef

    return f1, f2


def rk4_step(f1, f2, indep, dep1, dep2, h):
    """One classical RK4 step for a coupled pair (dep1', dep2')."""
    k1_1 = h * f1(indep, dep1, dep2)
    k1_2 = h * f2(indep, dep1, dep2)

    k2_1 = h * f1(indep + h / 2, dep1 + k1_1 / 2, dep2 + k1_2 / 2)
    k2_2 = h * f2(indep + h / 2, dep1 + k1_1 / 2, dep2 + k1_2 / 2)

    k3_1 = h * f1(indep + h / 2, dep1 + k2_1 / 2, dep2 + k2_2 / 2)
    k3_2 = h * f2(indep + h / 2, dep1 + k2_1 / 2, dep2 + k2_2 / 2)

    k4_1 = h * f1(indep + h, dep1 + k3_1, dep2 + k3_2)
    k4_2 = h * f2(indep + h, dep1 + k3_1, dep2 + k3_2)

    next_dep1 = dep1 + (k1_1 + 2 * k2_1 + 2 * k3_1 + k4_1) / 6
    next_dep2 = dep2 + (k1_2 + 2 * k2_2 + 2 * k3_2 + k4_2) / 6
    return next_dep1, next_dep2


def eval_closed_form(expr, indep_array, var):
    """Vector-evaluate a user closed-form f(var) over the solution grid.

    Returns a list (NaN/Inf -> None for clean Plotly gaps), or None on failure.
    """
    if not expr:
        return None
    try:
        arr = np.asarray(indep_array, dtype=float)
        local = {var: arr, "x": arr, "t": arr}
        result = eval(validate_and_compile(expr), EVAL_GLOBALS, local)
        result = np.broadcast_to(np.asarray(result, dtype=float), arr.shape)
        return [None if (np.isnan(v) or np.isinf(v)) else float(v) for v in result]
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.route("/solve", methods=["POST"])
def solve():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode", "single")  # 'single' (open-form ODE) | 'system'
    if mode in ("1st", "2nd"):         # backwards compatibility
        mode = "single"

    try:
        indep0 = float(data.get("indep0", 0))
        dep1_0 = float(data.get("dep1_0", 1))
        dep2_0 = float(data.get("dep2_0", 0))
        indep_end = float(data.get("indep_end", 5))

        span = indep_end - indep0
        if span == 0:
            return jsonify({"error": "Start and End values are identical."}), 400

        h = math.copysign(H, span)               # integrate the correct direction
        steps = min(int(abs(span) / H), MAX_STEPS)

        order = None
        if mode == "system":
            expr1 = parse_expr(data.get("eq1", ""))
            expr2 = parse_expr(data.get("eq2", ""))
            f1 = make_callable(expr1, "system")
            f2 = make_callable(expr2, "system")
            parsed1, parsed2 = expr1, expr2
        else:  # single open-form ODE; order auto-detected
            order, code = build_single(data.get("eq1", ""))
            f1, f2 = make_single_callable(code, order)
            parsed1, parsed2 = describe_single(data.get("eq1", ""), order), ""

        indep_pts = [indep0]
        dep1_pts = [dep1_0]
        dep2_pts = [dep2_0]
        curr_indep, curr_dep1, curr_dep2 = indep0, dep1_0, dep2_0
        truncated = False
        track_dep2 = (mode == "system") or (order == 2)

        for _ in range(steps):
            try:
                curr_dep1, curr_dep2 = rk4_step(
                    f1, f2, curr_indep, curr_dep1, curr_dep2, h)
            except (OverflowError, ValueError, ZeroDivisionError,
                    FloatingPointError):
                truncated = True
                break

            if (not np.isfinite(curr_dep1)) or abs(curr_dep1) > 1e150:
                truncated = True
                break
            if track_dep2 and ((not np.isfinite(curr_dep2))
                               or abs(curr_dep2) > 1e150):
                truncated = True
                break

            curr_indep += h
            indep_pts.append(curr_indep)
            dep1_pts.append(curr_dep1)
            dep2_pts.append(curr_dep2)

        # Optional: overlay a user-supplied closed form to check the solution.
        check_raw = data.get("check", "")
        check_var = "t" if mode == "system" else "x"
        check_pts = eval_closed_form(parse_expr(check_raw), indep_pts, check_var) \
            if check_raw else None

        return jsonify({
            "indep": indep_pts,
            "dep1": dep1_pts,
            "dep2": dep2_pts,
            "check": check_pts,
            "step_count": len(indep_pts),
            "truncated": truncated,
            "order": order,
            "parsed1": parsed1,
            "parsed2": parsed2,
        })

    except (TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid input: {e}"}), 400
    except SyntaxError:
        return jsonify({"error": "Could not parse the equation."}), 400
    except Exception as e:  # last-resort guard
        return jsonify({"error": f"Evaluation error: {e}"}), 400


def describe_single(eq_raw, order):
    """A short human-readable note of what was parsed (for the status line)."""
    raw = (eq_raw or "").strip()
    label = "2nd-order" if order == 2 else "1st-order"
    return f"{label}: {raw}" if raw else label


# ----------------------------------------------------------------------------
# Symbolic differentiation
# ----------------------------------------------------------------------------
@app.route("/differentiate", methods=["POST"])
def differentiate():
    data = request.get_json(force=True, silent=True) or {}
    try:
        expr = to_sympy(data.get("expr", ""))
        free = sorted(str(s) for s in expr.free_symbols)
        var_name = data.get("var") or (free[0] if free else "x")
        if var_name not in SYM_VARS:
            return jsonify({"error": f"cannot differentiate with respect to {var_name}"}), 400

        order = int(data.get("order", 1) or 1)
        order = max(1, min(order, 5))
        result = sp.diff(expr, SYM_VARS[var_name], order)

        return jsonify({
            "latex": sp.latex(result),
            "plain": str(result),
            "variables": free or ["x"],
            "var_used": var_name,
        })
    except (ValueError, SyntaxError) as e:
        return jsonify({"error": f"Invalid input: {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"Could not differentiate: {e}"}), 400


# ----------------------------------------------------------------------------
# Symbolic / numeric integration (single..triple, line, flux)
# ----------------------------------------------------------------------------
def _bounds(data, key):
    """Read [var, a, b] bound triples; sympify the limits so pi etc. work."""
    out = []
    for b in data.get(key, []):
        var = SYM_VARS[b[0]]
        lo = sp.sympify(parse_expr(str(b[1])), locals=SYMPY_LOCALS)
        hi = sp.sympify(parse_expr(str(b[2])), locals=SYMPY_LOCALS)
        out.append((var, lo, hi))
    return out


def _finish(integral):
    """Evaluate an Integral both symbolically and numerically where possible."""
    out = {"setup_latex": sp.latex(integral)}
    closed = None
    try:
        closed = integral.doit()
    except Exception:
        closed = None

    if closed is not None and not closed.has(sp.Integral):
        out["latex"] = sp.latex(closed)
        out["plain"] = str(closed)
        if not closed.free_symbols:
            try:
                out["numeric"] = float(closed.evalf())
            except Exception:
                pass
    else:
        # No closed form -> numeric (definite integrals only).
        try:
            val = integral.evalf()
            out["numeric"] = float(val)
            out["latex"] = sp.latex(integral)
            out["plain"] = "(no elementary closed form)"
        except Exception:
            out["error_note"] = "could not evaluate"
    return out


@app.route("/integrate", methods=["POST"])
def integrate_route():
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind", "single")
    coords = data.get("coords", "cartesian")
    try:
        t, u, v = SYM_VARS["t"], SYM_VARS["u"], SYM_VARS["v"]
        x, y, z = SYM_VARS["x"], SYM_VARS["y"], SYM_VARS["z"]
        r, th, ph, rho = (SYM_VARS["r"], SYM_VARS["theta"],
                          SYM_VARS["phi"], SYM_VARS["rho"])

        if kind in ("single", "double", "triple"):
            f = to_sympy(data.get("integrand", "0"))
            bounds = _bounds(data, "bounds")

            if coords == "polar":
                f = f * r                      # dA = r dr dθ
            elif coords == "cylindrical":
                f = f * r                      # dV = r dr dθ dz
            elif coords == "spherical":
                f = f * rho**2 * sp.sin(ph)    # dV = ρ² sinφ dρ dθ dφ

            if bounds:
                integral = sp.Integral(f, *bounds)
            else:  # indefinite single integral
                var = SYM_VARS[data.get("var", "x")]
                integral = sp.Integral(f, var)
            result = _finish(integral)

        elif kind == "line":
            # curve r(t) = (x(t), y(t), z(t)); z optional
            cx = to_sympy(data.get("cx", "0"))
            cy = to_sympy(data.get("cy", "0"))
            cz = to_sympy(data.get("cz", "")) if data.get("cz") else sp.Integer(0)
            (tv, a, b) = _bounds(data, "bounds")[0]
            dx, dy_, dz = sp.diff(cx, tv), sp.diff(cy, tv), sp.diff(cz, tv)
            sub = {x: cx, y: cy, z: cz}

            if data.get("line_mode", "scalar") == "vector":
                P = to_sympy(data.get("P", "0")).subs(sub)
                Q = to_sympy(data.get("Q", "0")).subs(sub)
                R = to_sympy(data.get("R", "0")).subs(sub) if data.get("R") else sp.Integer(0)
                integrand = P * dx + Q * dy_ + R * dz
            else:  # scalar  ∫ f ds
                f = to_sympy(data.get("integrand", "0")).subs(sub)
                integrand = f * sp.sqrt(dx**2 + dy_**2 + dz**2)
            result = _finish(sp.Integral(integrand, (tv, a, b)))

        elif kind == "flux2d":
            # ∮ F·n ds across plane curve = ∫ (P y' - Q x') dt
            cx = to_sympy(data.get("cx", "0"))
            cy = to_sympy(data.get("cy", "0"))
            (tv, a, b) = _bounds(data, "bounds")[0]
            sub = {x: cx, y: cy}
            P = to_sympy(data.get("P", "0")).subs(sub)
            Q = to_sympy(data.get("Q", "0")).subs(sub)
            integrand = P * sp.diff(cy, tv) - Q * sp.diff(cx, tv)
            result = _finish(sp.Integral(integrand, (tv, a, b)))

        elif kind == "flux3d":
            # ∫∫ F·(r_u × r_v) du dv for surface r(u,v)
            sx = to_sympy(data.get("sx", "0"))
            sy = to_sympy(data.get("sy", "0"))
            sz = to_sympy(data.get("sz", "0"))
            bnds = _bounds(data, "bounds")
            (uv, ua, ub) = bnds[0]
            (vv, va, vb) = bnds[1]
            ru = sp.Matrix([sp.diff(sx, uv), sp.diff(sy, uv), sp.diff(sz, uv)])
            rv = sp.Matrix([sp.diff(sx, vv), sp.diff(sy, vv), sp.diff(sz, vv)])
            n = ru.cross(rv)
            sub = {x: sx, y: sy, z: sz}
            F = sp.Matrix([to_sympy(data.get("P", "0")).subs(sub),
                           to_sympy(data.get("Q", "0")).subs(sub),
                           to_sympy(data.get("R", "0")).subs(sub)])
            integrand = F.dot(n)
            result = sp.Integral(integrand, (uv, ua, ub), (vv, va, vb))
            result = _finish(result)
        else:
            return jsonify({"error": f"unknown integral kind: {kind}"}), 400

        return jsonify(result)

    except (ValueError, SyntaxError, IndexError, KeyError) as e:
        return jsonify({"error": f"Invalid input: {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"Could not integrate: {e}"}), 400


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    # debug=False by default. Set FLASK_DEBUG=1 locally if you want the reloader;
    # never enable it in production (it exposes an interactive RCE console).
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)