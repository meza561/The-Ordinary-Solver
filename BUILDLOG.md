# Build Log

## Week 1 (June 5 – June 8)

### June 5 — Day 1: Testing infrastructure
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

