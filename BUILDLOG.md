# Build Log

## Week 1 (June 5 – June 8)

### June 5 — Day 1-2: Testing infrastructure
Set up pytest with pytest-cov. Created tests/ directory, conftest.py with
app and client fixtures, and pytest.ini configured for automatic coverage
reporting on every run.

Wrote the first 5 parser tests, including two regression tests for the
ydy/yddy bug we hit earlier (MathLive's y^{\prime} was getting parsed as
ydy because the old code only stripped the superscript). All 5 passing,
coverage at 20%.

Set up PyCharm's pytest runner so I can run individual tests with one
click — already feels faster than the terminal.

**Coverage:** 20% · **Tests:** 5 passing · **Commits:** 2

### June 6 — Day 3: Parser regressions + AST sandbox tests
Branched `parser-tests` off master and added 7 more parser tests covering
exponent braces, nested fractions, MathLive's `\sin\left(x\right)` form,
implicit-multiplication shielding for `log10(`, paren-paren multiplication,
and the Greek letters used in the integral tab's coordinate systems.

Branched `security-tests` independently and wrote 12 tests against the
AST whitelist validator. The "blocks" tests prove the sandbox holds
against the classic `().__class__` escape, the full subclass chain,
dunder attribute access on any variable, `__import__`, lambdas, list
comprehensions, string constants, unknown names, and calls to
non-whitelisted functions like `print`. The "allows" tests confirm
that legitimate arithmetic, math functions, and constants still work.

Merged both branches into master in sequence — first a fast-forward,
then a real merge commit (got trapped by vim briefly, escaped via `:wq`,
configured a friendlier editor for next time). Pushed everything.

**Coverage:** 25% · **Tests:** 24 passing · **Commits on master:** 5

### June 7 — Day 4: ODE solver tests
Created `ode-tests` branch and wrote 13 tests verifying the RK4 integrator
against classical analytical solutions. Coverage jumped from 25% to 57% in
a single file — the mathematical core is now verified end-to-end.

What's now tested and locked down:
- First-order: `y' = y` → e, `y' = x/y` → sqrt(x²+1)
- Second-order: `y'' + 4y = 0` → cos(2x), `y'' - y = 0` → e^x
- 2D system: circular motion (x'=y, y'=-x) returns to start after 2π
- Order auto-detection (1 vs 2) from open-form input
- Backward integration via copysign (regression test for the abs() bug)
- Step cap of 200k preventing runaway loops
- Asymptote/blow-up detection with truncated=True
- The f(x) candidate-overlay feature, both matching and non-matching cases

Fast-forward merge to master, pushed, branch deleted. Workflow is starting
to feel automatic.

**Coverage:** 57% · **Tests:** 37 passing · **Commits on master:** 7

### June 8 — Day 5: Symbolic differentiation and integration tests
Created `symbolic-tests` branch and wrote 17 tests covering the
`/differentiate` and `/integrate` endpoints. Coverage jumped from 57%
to 88% — the symbolic routes were almost entirely untested before today.

What's now verified:
- Differentiation: chain rule, product rule, partial derivatives, higher
  orders, variable list returned to the UI
- Single integrals (definite and indefinite)
- Double integrals — Cartesian, plus polar with automatic Jacobian
  (unit disk area = π proves the `r` factor is being applied)
- Triple integrals — spherical (unit ball = 4π/3, verifying ρ²sinφ),
  cylindrical (volume = 2π, verifying r)
- Line integrals — scalar (arc length 2π) and vector work (2π)
- Flux integrals — 2D divergence theorem case (2π) and 3D through a
  parametric disk (π)
- Numeric fallback for non-elementary integrands (∫e^(-x²) → erf)
- Sandbox still rejects malicious input on both symbolic endpoints

One test caught a real boundary: `a*x + b*y` was rejected because `a`
and `b` aren't in the variable whitelist. The test was wrong, not the
code — but it documents the actual scope of the differentiator and could
become a reason to expand the whitelist later if standard parameter
notation matters. Tightened the test to use x, y, z and moved on.

Fast-forward merge to master, pushed, branch deleted.

**Coverage:** 88% · **Tests:** 55 passing · **Commits on master:** 9