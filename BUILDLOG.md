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
