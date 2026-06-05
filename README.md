# The Ordinary Solver

A web-based math workbench with eight tabs: solve ODEs, differentiate and integrate symbolically, graph functions in 2D and 3D, run a scientific calculator, and fit linear or nonlinear trends to data.

Built with Flask, SymPy, NumPy, and Plotly.

## Features

- **ODE Solver** — RK4 integration for open-form single ODEs (`y'' + 3y' + 4y = 0`, `y' = x/y`, etc.; order auto-detected) and 2D systems. Optional candidate-solution overlay with a match/differ verdict.
- **Derivative** — symbolic differentiation with respect to any variable, up to 4th order.
- **Integral** — single, double, and triple integrals in Cartesian, polar, cylindrical, and spherical coordinates (Jacobian applied automatically). Also line integrals (scalar and vector) and flux integrals (2D across a curve, 3D through a parametric surface).
- **Scientific Calculator** — with DEG/RAD toggle and history.
- **Graphing Calculator** — plot multiple `y = f(x)` curves, live.
- **3D Surface** — plot `z = f(x, y)`, live.
- **LSRL** — least-squares regression line with slope, intercept, r, and r².
- **Nonlinear Fit** — quadratic, cubic, exponential, power, and logarithmic curve fits with R².

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## Tech stack

- **Backend:** Python, Flask, SymPy, NumPy
- **Frontend:** HTML/CSS, Tailwind, Plotly, math.js, MathLive, KaTeX

## Notes

This is a personal learning project; user expressions are validated through an AST whitelist before evaluation, but I don't recommend exposing it to the open internet without further review.
