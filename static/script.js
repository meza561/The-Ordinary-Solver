/* ============================================================
   The Ordinary Solver - client logic
   ============================================================ */

/* ---------- shared helpers ---------- */
const renderers = {};                       // re-draw hooks for theme flips

function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function themeVars() {
    const cs = getComputedStyle(document.body);
    return {
        text: cs.getPropertyValue("--text-color").trim() || "#1e293b",
        grid: cs.getPropertyValue("--plot-grid").trim() || "#e2e8f0",
        accent: cs.getPropertyValue("--accent").trim() || "#ea580c",
    };
}

function plotLayout({ title, xtitle, ytitle, extra } = {}) {
    const t = themeVars();
    return Object.assign({
        title: title ? { text: title, font: { size: 13 } } : undefined,
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: t.text, family: "IBM Plex Mono, monospace", size: 11 },
        margin: { t: 38, r: 20, b: 46, l: 56 },
        xaxis: { title: { text: xtitle, font: { size: 11 } }, gridcolor: t.grid, zerolinecolor: t.grid },
        yaxis: { title: { text: ytitle, font: { size: 11 } }, gridcolor: t.grid, zerolinecolor: t.grid },
    }, extra || {});
}

const PLOT_CONFIG = { responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"] };

function renderTex(el, tex, displayMode = true) {
    if (typeof katex === "undefined") { el.textContent = tex; return; }
    try { katex.render(tex, el, { throwOnError: false, displayMode }); }
    catch (_) { el.textContent = tex; }
}

const round = (v, p = 4) => {
    if (!isFinite(v)) return v;
    const f = Math.pow(10, p);
    return Math.round(v * f) / f;
};

/* parse a textarea of "x, y" rows into {xs, ys} */
function parsePairs(text) {
    const xs = [], ys = [];
    text.split("\n").forEach((line) => {
        const m = line.trim().split(/[\s,]+/).filter(Boolean);
        if (m.length >= 2) {
            const x = parseFloat(m[0]), y = parseFloat(m[1]);
            if (isFinite(x) && isFinite(y)) { xs.push(x); ys.push(y); }
        }
    });
    return { xs, ys };
}

/* ---------- theme toggle ---------- */
document.getElementById("theme-toggle").addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    document.body.classList.toggle("dark");
    Object.values(renderers).forEach((fn) => { try { fn(); } catch (_) {} });
});

/* ---------- tab switching ---------- */
const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");
tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
        tabButtons.forEach((b) => b.classList.remove("active"));
        tabPanels.forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const panel = document.getElementById("tab-" + btn.dataset.tab);
        panel.classList.add("active");
        panel.querySelectorAll(".js-plotly-plot").forEach((d) => {
            try { Plotly.Plots.resize(d); } catch (_) {}
        });
    });
});

/* ============================================================
   TAB 1 - ODE SOLVER (live, debounced server calls)
   ============================================================ */
(() => {
    const modeSelect = document.getElementById("mode-select");
    const eq1Label = document.getElementById("eq1-label");
    const eq2Container = document.getElementById("eq2-container");
    const eq2Label = document.getElementById("eq2-label");
    const indep0Label = document.getElementById("indep0-label");
    const dep1Label = document.getElementById("dep1-label");
    const dep2Container = document.getElementById("dep2-container");
    const dep2Label = document.getElementById("dep2-label");
    const independLabel = document.getElementById("independ-label");
    const graph2Container = document.getElementById("graph-canvas-2-container");
    const previewDiv = document.getElementById("analytical-preview");
    const statusDiv = document.getElementById("ode-status");

    function updateUI() {
        const mode = modeSelect.value;
        if (mode === "system") {
            eq1Label.classList.remove("hidden");
            eq1Label.innerText = "x' =";
            eq2Container.classList.remove("hidden");
            eq2Label.innerText = "y' =";
            dep2Container.classList.remove("hidden");
            indep0Label.innerText = "Start t\u2080";
            dep1Label.innerText = "Init x\u2080";
            dep2Label.innerText = "Init y\u2080";
            independLabel.innerText = "End t";
            graph2Container.classList.remove("hidden");
        } else {                       // single open-form ODE
            eq1Label.classList.add("hidden");   // user types the whole equation
            eq2Container.classList.add("hidden");
            dep2Container.classList.add("hidden");  // shown later iff 2nd order
            indep0Label.innerText = "Start x\u2080";
            dep1Label.innerText = "Init y\u2080";
            dep2Label.innerText = "Init y'\u2080";
            independLabel.innerText = "End x";
            graph2Container.classList.add("hidden");
        }
    }
    updateUI();

    let lastData = null;

    function renderPreview(mode, eq1, eq2) {
        if (typeof katex === "undefined") return;
        // Single mode: render the user's equation verbatim (it may include "=").
        const tex = mode === "system"
            ? `\\begin{cases} x' = ${eq1} \\\\ y' = ${eq2} \\end{cases}`
            : (eq1 || "");
        try { katex.render(tex, previewDiv, { throwOnError: false, displayMode: true }); }
        catch (_) { previewDiv.textContent = tex; }
    }

    function drawPlots(data, mode) {
        if (mode !== "system") {
            const traces = [{
                x: data.indep, y: data.dep1, type: "scatter", mode: "lines",
                line: { color: themeVars().accent, width: 2.5 }, name: "y(x)",
            }];
            if (data.check) traces.push({
                x: data.indep, y: data.check, type: "scatter", mode: "lines",
                line: { color: "#3b82f6", width: 2, dash: "dash" }, name: "f(x) check",
            });
            Plotly.react("graph-canvas-1", traces,
                plotLayout({ title: "Solution Curve", xtitle: "x", ytitle: "y",
                    extra: { showlegend: !!data.check, legend: { x: 0, y: 1 } } }), PLOT_CONFIG);
        } else {
            Plotly.react("graph-canvas-1", [
                { x: data.indep, y: data.dep1, type: "scatter", mode: "lines",
                  line: { color: themeVars().accent, width: 2 }, name: "x(t)" },
                { x: data.indep, y: data.dep2, type: "scatter", mode: "lines",
                  line: { color: "#3b82f6", width: 2 }, name: "y(t)" },
            ], plotLayout({ title: "Time Series", xtitle: "t", ytitle: "value",
                extra: { showlegend: true, legend: { x: 0, y: 1 } } }), PLOT_CONFIG);
            Plotly.react("graph-canvas-2", [{
                x: data.dep1, y: data.dep2, type: "scatter", mode: "lines",
                line: { color: "#10b981", width: 2 }, name: "phase",
            }], plotLayout({ title: "Phase Portrait", xtitle: "x(t)", ytitle: "y(t)" }), PLOT_CONFIG);
        }
    }
    renderers.ode = () => { if (lastData) drawPlots(lastData.data, lastData.mode); };

    async function solve() {
        const mode = modeSelect.value;
        const payload = {
            mode,
            eq1: document.getElementById("eq1-mathfield").value,
            eq2: document.getElementById("eq2-mathfield").value,
            check: document.getElementById("check-mathfield").value,
            indep0: document.getElementById("indep0-input").value,
            dep1_0: document.getElementById("dep1-input").value,
            dep2_0: document.getElementById("dep2-input").value,
            indep_end: document.getElementById("independ-input").value,
        };
        statusDiv.textContent = "Integrating\u2026";
        try {
            const res = await fetch("/solve", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (data.error) {
                previewDiv.innerHTML =
                    `<span style="color:#ef4444;font-family:monospace">${data.error}</span>`;
                statusDiv.textContent = ""; return;
            }
            renderPreview(mode, payload.eq1, payload.eq2);
            lastData = { data, mode };
            drawPlots(data, mode);

            // In single mode, show the y'0 field only when a 2nd-order ODE was detected.
            if (mode !== "system") {
                dep2Container.classList.toggle("hidden", data.order !== 2);
            }

            let msg = `${data.step_count.toLocaleString()} points`;
            if (mode === "system") msg += ` \u00b7 x' = ${data.parsed1} , y' = ${data.parsed2}`;
            else msg += ` \u00b7 ${data.parsed1}`;
            if (data.truncated) msg += "  \u26a0 stopped early (blow-up / asymptote)";
            if (data.check) msg += "  \u00b7 overlay plotted";
            statusDiv.textContent = msg;

            // f(x) candidate verdict: compare overlay to the numerical solution.
            const verdict = document.getElementById("check-verdict");
            if (mode !== "system" && data.check) {
                let maxErr = 0, count = 0;
                for (let i = 0; i < data.check.length; i++) {
                    const cVal = data.check[i], sVal = data.dep1[i];
                    if (cVal == null || !isFinite(cVal) || !isFinite(sVal)) continue;
                    maxErr = Math.max(maxErr, Math.abs(cVal - sVal));
                    count++;
                }
                if (count === 0) {
                    verdict.textContent = "could not evaluate";
                    verdict.style.color = "var(--text-muted)";
                } else if (maxErr < 1e-3) {
                    verdict.textContent = "\u2713 matches";
                    verdict.style.color = "#10b981";
                } else {
                    verdict.textContent = "\u2717 differs (\u0394\u2248" + maxErr.toPrecision(2) + ")";
                    verdict.style.color = "#ef4444";
                }
            } else if (verdict) {
                verdict.textContent = "";
            }
        } catch (err) {
            console.error(err); statusDiv.textContent = "Network / server error.";
        }
    }

    const liveSolve = debounce(solve, 450);
    // Live triggers: mode change re-lays-out then solves; everything else just solves.
    modeSelect.addEventListener("change", () => { updateUI(); liveSolve(); });
    ["eq1-mathfield", "eq2-mathfield", "check-mathfield"].forEach((id) =>
        document.getElementById(id).addEventListener("input", liveSolve));
    ["indep0-input", "dep1-input", "dep2-input", "independ-input"].forEach((id) =>
        document.getElementById(id).addEventListener("input", liveSolve));

    window.addEventListener("load", () => setTimeout(solve, 350));
})();

/* ============================================================
   TAB 2 - SCIENTIFIC CALCULATOR
   ============================================================ */
(() => {
    const sci = math.create(math.all);
    let angleMode = "rad";
    const toRad = (x) => (angleMode === "deg" ? (x * Math.PI) / 180 : x);
    const fromRad = (x) => (angleMode === "deg" ? (x * 180) / Math.PI : x);
    sci.import({
        sin: (x) => Math.sin(toRad(x)), cos: (x) => Math.cos(toRad(x)),
        tan: (x) => Math.tan(toRad(x)), asin: (x) => fromRad(Math.asin(x)),
        acos: (x) => fromRad(Math.acos(x)), atan: (x) => fromRad(Math.atan(x)),
        ln: (x) => Math.log(x),
    }, { override: true });

    const input = document.getElementById("calc-input");
    const resultEl = document.getElementById("calc-result");
    const historyEl = document.getElementById("calc-history");
    let lastAns = 0;

    function insertAtCursor(text) {
        const s = input.selectionStart ?? input.value.length;
        const e = input.selectionEnd ?? input.value.length;
        input.value = input.value.slice(0, s) + text + input.value.slice(e);
        const p = s + text.length;
        input.focus(); input.setSelectionRange(p, p); livePreview();
    }
    function fmt(v) {
        if (typeof v === "number") return isFinite(v) ? sci.format(v, { precision: 12 }) : "\u221e";
        return v.toString();
    }
    function livePreview() {
        const expr = input.value.trim();
        if (!expr) { resultEl.textContent = "= 0"; return; }
        try { resultEl.textContent = "= " + fmt(sci.evaluate(expr, { ans: lastAns })); }
        catch (_) { resultEl.textContent = "\u2026"; }
    }
    function evaluate() {
        const expr = input.value.trim();
        if (!expr) return;
        try {
            const v = sci.evaluate(expr, { ans: lastAns });
            const out = fmt(v);
            lastAns = typeof v === "number" ? v : lastAns;
            resultEl.textContent = "= " + out;
            const row = document.createElement("div");
            row.className = "border-b pb-1 cursor-pointer";
            row.style.borderColor = "var(--border-soft)";
            row.innerHTML = `<div class="text-muted-c text-xs">${expr}</div>` +
                            `<div class="text-accent">= ${out}</div>`;
            row.addEventListener("click", () => insertAtCursor(out));
            historyEl.prepend(row);
        } catch (_) { resultEl.textContent = "Error"; }
    }

    document.querySelectorAll("#tab-sci .calc-key").forEach((key) => {
        key.addEventListener("click", () => {
            if (key.dataset.act === "eval") return evaluate();
            if (key.dataset.act === "clear") { input.value = ""; livePreview(); input.focus(); return; }
            if (key.dataset.act === "del") {
                const p = input.selectionStart ?? input.value.length;
                if (p > 0) { input.value = input.value.slice(0, p - 1) + input.value.slice(p); input.setSelectionRange(p - 1, p - 1); }
                livePreview(); input.focus(); return;
            }
            insertAtCursor(key.dataset.ins);
        });
    });
    input.addEventListener("input", livePreview);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); evaluate(); } });
    document.querySelectorAll("#angle-toggle button").forEach((b) => {
        b.addEventListener("click", () => {
            angleMode = b.dataset.angle;
            document.querySelectorAll("#angle-toggle button").forEach((x) => x.classList.toggle("active", x === b));
            livePreview();
        });
    });
    document.getElementById("calc-clear-history").addEventListener("click", () => historyEl.innerHTML = "");
})();

/* ---------- shared math.js for graphers (radians + ln) ---------- */
math.import({ ln: (x) => math.log(x) }, { override: true });
const GRAPH_COLORS = ["#ea580c", "#3b82f6", "#10b981", "#a855f7", "#e11d48", "#0891b2"];

/* ============================================================
   TAB 3 - GRAPHING (2D, live)
   ============================================================ */
(() => {
    const list = document.getElementById("func-list");
    const statusEl = document.getElementById("graph-2d-status");
    let colorIdx = 0;
    const livePlot = debounce(plot, 250);

    function addRow(initial = "") {
        const color = GRAPH_COLORS[colorIdx++ % GRAPH_COLORS.length];
        const row = document.createElement("div");
        row.className = "func-row";
        row.dataset.color = color;
        row.innerHTML =
            `<span class="color-dot" style="background:${color}"></span>` +
            `<span class="mono text-muted-c text-sm">y=</span>` +
            `<input type="text" spellcheck="false" value="${initial}" ` +
            `class="flex-1 p-1.5 text-sm border rounded mono bg-transparent func-expr">` +
            `<button class="wolfram-theme-btn border rounded px-2 py-1 text-xs func-del">\u2715</button>`;
        row.querySelector(".func-del").addEventListener("click", () => {
            if (list.children.length > 1) { row.remove(); plot(); }
        });
        row.querySelector(".func-expr").addEventListener("input", livePlot);
        list.appendChild(row);
    }

    function plot() {
        const xmin = parseFloat(document.getElementById("g-xmin").value);
        const xmax = parseFloat(document.getElementById("g-xmax").value);
        let n = parseInt(document.getElementById("g-samples").value, 10);
        if (!isFinite(xmin) || !isFinite(xmax) || xmax <= xmin) { statusEl.textContent = "Check the x-range."; return; }
        n = Math.max(50, Math.min(n || 800, 5000));
        const dx = (xmax - xmin) / (n - 1);
        const traces = [], errors = [];
        list.querySelectorAll(".func-row").forEach((row) => {
            const expr = row.querySelector(".func-expr").value.trim();
            if (!expr) return;
            let node;
            try { node = math.compile(expr); } catch (_) { errors.push(`${expr}: parse error`); return; }
            const xs = [], ys = [];
            for (let i = 0; i < n; i++) {
                const x = xmin + i * dx; xs.push(x);
                let y; try { y = node.evaluate({ x }); } catch (_) { y = null; }
                ys.push(typeof y === "number" && isFinite(y) ? y : null);
            }
            traces.push({ x: xs, y: ys, type: "scatter", mode: "lines",
                line: { color: row.dataset.color, width: 2 }, name: "y=" + expr, connectgaps: false });
        });
        if (!traces.length) { statusEl.textContent = "Enter a function."; Plotly.react("graph-2d-canvas", [], plotLayout({ xtitle: "x", ytitle: "y" }), PLOT_CONFIG); return; }
        Plotly.react("graph-2d-canvas", traces,
            plotLayout({ xtitle: "x", ytitle: "y", extra: { showlegend: true, legend: { x: 0, y: 1.12, orientation: "h" } } }), PLOT_CONFIG);
        statusEl.textContent = errors.length ? errors.join("  \u00b7  ") : `${traces.length} function(s) \u00b7 updating live`;
    }
    renderers.graph2d = () => { if (document.getElementById("graph-2d-canvas").data) plot(); };

    document.getElementById("add-func").addEventListener("click", () => { addRow(""); });
    ["g-xmin", "g-xmax", "g-samples"].forEach((id) => document.getElementById(id).addEventListener("input", livePlot));
    addRow("x^2 - 4"); addRow("sin(x)");
    plot();
})();

/* ============================================================
   TAB 4 - 3D SURFACE (live)
   ============================================================ */
(() => {
    const statusEl = document.getElementById("graph-3d-status");
    const livePlot = debounce(plot, 350);

    function plot() {
        const expr = document.getElementById("surf-expr").value.trim();
        const xmin = parseFloat(document.getElementById("s-xmin").value);
        const xmax = parseFloat(document.getElementById("s-xmax").value);
        const ymin = parseFloat(document.getElementById("s-ymin").value);
        const ymax = parseFloat(document.getElementById("s-ymax").value);
        let res = parseInt(document.getElementById("s-res").value, 10);
        if (!expr) { statusEl.textContent = "Enter an expression."; return; }
        if (!(xmax > xmin) || !(ymax > ymin)) { statusEl.textContent = "Check the x / y ranges."; return; }
        res = Math.max(10, Math.min(res || 55, 150));
        let node; try { node = math.compile(expr); } catch (_) { statusEl.textContent = "Parse error in z(x,y)."; return; }
        const xs = [], ys = [], z = [];
        for (let i = 0; i < res; i++) xs.push(xmin + (xmax - xmin) * i / (res - 1));
        for (let j = 0; j < res; j++) ys.push(ymin + (ymax - ymin) * j / (res - 1));
        for (let j = 0; j < res; j++) {
            const rowz = [];
            for (let i = 0; i < res; i++) {
                let v; try { v = node.evaluate({ x: xs[i], y: ys[j] }); } catch (_) { v = null; }
                rowz.push(typeof v === "number" && isFinite(v) ? v : null);
            }
            z.push(rowz);
        }
        const t = themeVars();
        Plotly.react("graph-3d-canvas", [{
            type: "surface", x: xs, y: ys, z, colorscale: "Viridis", showscale: false,
            contours: { z: { show: true, usecolormap: true, width: 1 } },
        }], {
            paper_bgcolor: "transparent",
            font: { color: t.text, family: "IBM Plex Mono, monospace", size: 11 },
            margin: { t: 10, r: 10, b: 10, l: 10 },
            scene: {
                xaxis: { title: "x", gridcolor: t.grid, color: t.text },
                yaxis: { title: "y", gridcolor: t.grid, color: t.text },
                zaxis: { title: "z", gridcolor: t.grid, color: t.text },
            },
        }, PLOT_CONFIG);
        statusEl.textContent = `${res}\u00d7${res} grid \u00b7 updating live`;
    }
    renderers.surface = () => { if (document.getElementById("graph-3d-canvas").data) plot(); };
    ["surf-expr", "s-xmin", "s-xmax", "s-ymin", "s-ymax", "s-res"].forEach((id) =>
        document.getElementById(id).addEventListener("input", livePlot));
    plot();
})();

/* ---------- regression helpers ---------- */
function linearFit(xs, ys) {
    const n = xs.length;
    let sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0;
    for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; sxx += xs[i] * xs[i]; sxy += xs[i] * ys[i]; syy += ys[i] * ys[i]; }
    const denom = n * sxx - sx * sx;
    const b = denom === 0 ? 0 : (n * sxy - sx * sy) / denom;
    const a = (sy - b * sx) / n;
    const rden = Math.sqrt(denom * (n * syy - sy * sy));
    const r = rden === 0 ? 0 : (n * sxy - sx * sy) / rden;
    return { a, b, r, r2: r * r };
}
function rSquared(ys, preds) {
    const ybar = ys.reduce((s, y) => s + y, 0) / ys.length;
    let ssTot = 0, ssRes = 0;
    for (let i = 0; i < ys.length; i++) { ssTot += (ys[i] - ybar) ** 2; ssRes += (ys[i] - preds[i]) ** 2; }
    return ssTot === 0 ? 1 : 1 - ssRes / ssTot;
}
function polyFit(xs, ys, deg) {
    const X = xs.map((x) => { const row = []; for (let k = 0; k <= deg; k++) row.push(Math.pow(x, k)); return row; });
    const Xt = math.transpose(X);
    const c = math.lusolve(math.multiply(Xt, X), math.multiply(Xt, ys));
    return c.map((r) => r[0]); // low -> high order
}
function polyPredict(coeffs, x) { return coeffs.reduce((s, c, k) => s + c * Math.pow(x, k), 0); }

/* ============================================================
   TAB 5 - LSRL
   ============================================================ */
(() => {
    const dataEl = document.getElementById("lsrl-data");
    const eqnEl = document.getElementById("lsrl-eqn");
    const statsEl = document.getElementById("lsrl-stats");
    const statusEl = document.getElementById("lsrl-status");
    let last = null;

    function compute() {
        const { xs, ys } = parsePairs(dataEl.value);
        if (xs.length < 2) {
            statusEl.textContent = "Need at least 2 points.";
            eqnEl.textContent = "\u0177 = \u2026"; statsEl.innerHTML = ""; return;
        }
        const { a, b, r, r2 } = linearFit(xs, ys);
        eqnEl.innerHTML = `\u0177 = ${round(b, 4)}x ${b >= 0 ? "+" : "\u2212"} ${Math.abs(round(a, 4))}`;
        statsEl.innerHTML =
            box("slope", round(b, 5)) + box("intercept", round(a, 5)) +
            box("r", round(r, 5)) + box("r\u00b2", round(r2, 5)) + box("n", xs.length);
        statusEl.textContent = "updating live";
        last = { xs, ys, a, b };
        draw();
    }
    function draw() {
        if (!last) return;
        const { xs, ys, a, b } = last;
        const xmin = Math.min(...xs), xmax = Math.max(...xs);
        const pad = (xmax - xmin) * 0.05 || 1;
        const lx = [xmin - pad, xmax + pad];
        Plotly.react("lsrl-canvas", [
            { x: xs, y: ys, type: "scatter", mode: "markers", name: "data",
              marker: { color: "#3b82f6", size: 8 } },
            { x: lx, y: lx.map((x) => a + b * x), type: "scatter", mode: "lines",
              name: "LSRL", line: { color: themeVars().accent, width: 2.5 } },
        ], plotLayout({ xtitle: "x", ytitle: "y", extra: { showlegend: true, legend: { x: 0, y: 1 } } }), PLOT_CONFIG);
    }
    renderers.lsrl = draw;
    dataEl.addEventListener("input", debounce(compute, 250));
    compute();
})();

/* ============================================================
   TAB 6 - NONLINEAR FIT
   ============================================================ */
(() => {
    const dataEl = document.getElementById("fit-data");
    const modelEl = document.getElementById("fit-model");
    const eqnEl = document.getElementById("fit-eqn");
    const statsEl = document.getElementById("fit-stats");
    const statusEl = document.getElementById("fit-status");
    let last = null;

    function fit(model, xs, ys) {
        const n = xs.length;
        if (model === "quad" || model === "cubic") {
            const deg = model === "quad" ? 2 : 3;
            if (n < deg + 1) return { error: `Need at least ${deg + 1} points.` };
            const c = polyFit(xs, ys, deg);
            const predict = (x) => polyPredict(c, x);
            const terms = c.map((v, k) => k === 0 ? `${round(v, 4)}`
                : `${round(v, 4)}x${k > 1 ? "^" + k : ""}`).reverse();
            return { predict, eqn: "\u0177 = " + terms.join(" + ").replace(/\+ -/g, "\u2212 ") };
        }
        if (model === "exp") { // y = a e^{bx}, need y > 0
            if (ys.some((y) => y <= 0)) return { error: "Exponential needs all y > 0." };
            const f = linearFit(xs, ys.map(Math.log));
            const a = Math.exp(f.a), b = f.b;
            return { predict: (x) => a * Math.exp(b * x), eqn: `\u0177 = ${round(a, 4)}\u00b7e^(${round(b, 4)}x)` };
        }
        if (model === "power") { // y = a x^b, need x>0, y>0
            if (xs.some((x) => x <= 0) || ys.some((y) => y <= 0)) return { error: "Power needs all x > 0 and y > 0." };
            const f = linearFit(xs.map(Math.log), ys.map(Math.log));
            const a = Math.exp(f.a), b = f.b;
            return { predict: (x) => a * Math.pow(x, b), eqn: `\u0177 = ${round(a, 4)}\u00b7x^(${round(b, 4)})` };
        }
        if (model === "log") { // y = a + b ln x, need x > 0
            if (xs.some((x) => x <= 0)) return { error: "Logarithmic needs all x > 0." };
            const f = linearFit(xs.map(Math.log), ys);
            return { predict: (x) => f.a + f.b * Math.log(x),
                eqn: `\u0177 = ${round(f.a, 4)} ${f.b >= 0 ? "+" : "\u2212"} ${Math.abs(round(f.b, 4))}\u00b7ln x` };
        }
    }

    function compute() {
        const { xs, ys } = parsePairs(dataEl.value);
        if (xs.length < 2) {
            statusEl.textContent = "Need at least 2 points.";
            eqnEl.textContent = "\u0177 = \u2026"; statsEl.innerHTML = ""; return;
        }
        const res = fit(modelEl.value, xs, ys);
        if (res.error) {
            statusEl.textContent = res.error; eqnEl.textContent = "\u0177 = \u2026"; statsEl.innerHTML = "";
            last = null; Plotly.react("fit-canvas", [{ x: xs, y: ys, type: "scatter", mode: "markers", marker: { color: "#3b82f6", size: 8 } }], plotLayout({ xtitle: "x", ytitle: "y" }), PLOT_CONFIG);
            return;
        }
        const preds = xs.map(res.predict);
        const r2 = rSquared(ys, preds);
        eqnEl.innerHTML = res.eqn;
        statsEl.innerHTML = box("model", modelEl.options[modelEl.selectedIndex].text.split("\u00a0")[0]) +
            box("R\u00b2", round(r2, 5)) + box("n", xs.length);
        statusEl.textContent = "updating live";
        last = { xs, ys, predict: res.predict };
        draw();
    }
    function draw() {
        if (!last) return;
        const { xs, ys, predict } = last;
        const xmin = Math.min(...xs), xmax = Math.max(...xs);
        const pad = (xmax - xmin) * 0.05 || 1;
        const N = 200, cx = [], cy = [];
        for (let i = 0; i < N; i++) {
            const x = (xmin - pad) + (xmax - xmin + 2 * pad) * i / (N - 1);
            cx.push(x); const y = predict(x); cy.push(isFinite(y) ? y : null);
        }
        Plotly.react("fit-canvas", [
            { x: xs, y: ys, type: "scatter", mode: "markers", name: "data", marker: { color: "#3b82f6", size: 8 } },
            { x: cx, y: cy, type: "scatter", mode: "lines", name: "fit", line: { color: themeVars().accent, width: 2.5 }, connectgaps: false },
        ], plotLayout({ xtitle: "x", ytitle: "y", extra: { showlegend: true, legend: { x: 0, y: 1 } } }), PLOT_CONFIG);
    }
    renderers.fit = draw;
    dataEl.addEventListener("input", debounce(compute, 250));
    modelEl.addEventListener("change", compute);
    compute();
})();

/* small stat-box helper */
function box(k, v) {
    return `<div class="stat-box"><div class="k">${k}</div><div class="v">${v}</div></div>`;
}

/* ============================================================
   TAB - DERIVATIVE (symbolic, via /differentiate)
   ============================================================ */
(() => {
    const input = document.getElementById("deriv-input");
    const go = document.getElementById("deriv-go");
    const resultEl = document.getElementById("deriv-result");
    const controls = document.getElementById("deriv-controls");
    const varSel = document.getElementById("deriv-var");
    const orderSel = document.getElementById("deriv-order");
    const plainEl = document.getElementById("deriv-plain");

    async function differentiate(useSelectedVar) {
        const expr = input.value;
        if (!expr || !expr.trim()) return;
        resultEl.textContent = "\u2026";
        try {
            const res = await fetch("/differentiate", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    expr,
                    var: useSelectedVar ? varSel.value : undefined,
                    order: orderSel.value,
                }),
            });
            const d = await res.json();
            if (d.error) {
                resultEl.innerHTML = `<span style="color:#ef4444">${d.error}</span>`;
                controls.classList.add("hidden");
                return;
            }
            renderTex(resultEl, d.latex);
            plainEl.textContent = d.plain;
            // Populate the variable picker with detected variables (the option the
            // user gets *after* clicking the arrow), keeping the one just used.
            varSel.innerHTML = d.variables
                .map((v) => `<option value="${v}"${v === d.var_used ? " selected" : ""}>${v}</option>`)
                .join("");
            controls.classList.remove("hidden");
        } catch (_) { resultEl.textContent = "Server error."; }
    }

    go.addEventListener("click", () => differentiate(false));
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); differentiate(false); }
    });
    varSel.addEventListener("change", () => differentiate(true));
    orderSel.addEventListener("change", () => differentiate(true));
})();

/* ============================================================
   TAB - INTEGRAL (symbolic + numeric, via /integrate)
   ============================================================ */
(() => {
    const kindSel = document.getElementById("int-kind");
    const coordsWrap = document.getElementById("int-coords-wrap");
    const coordsSel = document.getElementById("int-coords");
    const subWrap = document.getElementById("int-sub-wrap");
    const subLabel = document.getElementById("int-sub-label");
    const subSel = document.getElementById("int-sub");
    const form = document.getElementById("int-form");
    const statusEl = document.getElementById("int-status");
    const setupEl = document.getElementById("int-setup");
    const resultEl = document.getElementById("int-result");
    const numericEl = document.getElementById("int-numeric");

    const opt = (v, l) => `<option value="${v}">${l}</option>`;
    const val = (id) => { const el = document.getElementById(id); return el ? el.value : ""; };

    function field(id, label, ph, v = "") {
        return `<div class="flex items-center gap-2">
            <span class="mono text-sm text-muted-c w-28 text-right">${label}</span>
            <input id="${id}" type="text" spellcheck="false" value="${v}" placeholder="${ph}"
                class="flex-1 p-1.5 text-sm border rounded mono bg-transparent"></div>`;
    }
    function bounds(rows) {
        return rows.map(([v, label, lo, hi]) =>
            `<div class="bound-row flex items-center gap-2" data-var="${v}">
                <span class="mono text-sm text-muted-c w-28 text-right">${label}</span>
                <input class="blo flex-1 p-1.5 text-sm border rounded mono bg-transparent" type="text" value="${lo}" placeholder="lower">
                <span class="text-muted-c text-sm">to</span>
                <input class="bhi flex-1 p-1.5 text-sm border rounded mono bg-transparent" type="text" value="${hi}" placeholder="upper">
            </div>`).join("");
    }
    const divider = `<div class="pt-1 border-t" style="border-color:var(--border-soft)"></div>`;

    function refreshSelectors() {
        const kind = kindSel.value;
        if (kind === "double") {
            coordsWrap.classList.remove("hidden");
            coordsSel.innerHTML = opt("cartesian", "Cartesian (x, y)") + opt("polar", "Polar (r, \u03b8)");
        } else if (kind === "triple") {
            coordsWrap.classList.remove("hidden");
            coordsSel.innerHTML = opt("cartesian", "Cartesian (x, y, z)") +
                opt("cylindrical", "Cylindrical (r, \u03b8, z)") +
                opt("spherical", "Spherical (\u03c1, \u03b8, \u03c6)");
        } else {
            coordsWrap.classList.add("hidden");
        }
        if (kind === "line") {
            subWrap.classList.remove("hidden"); subLabel.textContent = "Mode";
            subSel.innerHTML = opt("scalar", "Scalar  \u222b f ds") + opt("vector", "Vector  \u222b F\u00b7dr");
        } else if (kind === "flux") {
            subWrap.classList.remove("hidden"); subLabel.textContent = "Type";
            subSel.innerHTML = opt("2d", "Across plane curve (2D)") + opt("3d", "Through surface (3D)");
        } else {
            subWrap.classList.add("hidden");
        }
        renderForm();
    }

    function renderForm() {
        const kind = kindSel.value, coords = coordsSel.value, sub = subSel.value;
        let h = "";
        if (kind === "single") {
            h += field("f_int", "\u222b f(x) dx", "e.g. x^2", "x^2");
            h += `<label class="flex items-center gap-2 text-sm mono text-muted-c"><input id="int-definite" type="checkbox" checked> definite</label>`;
            h += `<div id="single-bounds">` + bounds([["x", "x:", "0", "1"]]) + `</div>`;
        } else if (kind === "double") {
            if (coords === "polar") {
                h += field("f_int", "f(r, \u03b8)", "e.g. 1", "1");
                h += bounds([["r", "r:", "0", "1"], ["theta", "\u03b8:", "0", "2*pi"]]);
            } else {
                h += field("f_int", "f(x, y)", "e.g. x*y", "x*y");
                h += bounds([["x", "x:", "0", "1"], ["y", "y:", "0", "2"]]);
            }
        } else if (kind === "triple") {
            if (coords === "cylindrical") {
                h += field("f_int", "f(r, \u03b8, z)", "e.g. 1", "1");
                h += bounds([["r", "r:", "0", "1"], ["theta", "\u03b8:", "0", "2*pi"], ["z", "z:", "0", "2"]]);
            } else if (coords === "spherical") {
                h += field("f_int", "f(\u03c1, \u03b8, \u03c6)", "e.g. 1", "1");
                h += bounds([["rho", "\u03c1:", "0", "1"], ["theta", "\u03b8:", "0", "2*pi"], ["phi", "\u03c6:", "0", "pi"]]);
            } else {
                h += field("f_int", "f(x, y, z)", "e.g. 1", "1");
                h += bounds([["x", "x:", "0", "1"], ["y", "y:", "0", "1"], ["z", "z:", "0", "1"]]);
            }
        } else if (kind === "line") {
            if (sub === "vector") {
                h += field("F_P", "P  (i)", "e.g. -y", "-y") + field("F_Q", "Q  (j)", "e.g. x", "x") + field("F_R", "R  (k)", "optional", "");
            } else {
                h += field("f_int", "f(x, y, z)", "e.g. 1", "1");
            }
            h += divider;
            h += field("c_x", "x(t)", "e.g. cos(t)", "cos(t)") + field("c_y", "y(t)", "e.g. sin(t)", "sin(t)") + field("c_z", "z(t)", "optional", "");
            h += bounds([["t", "t:", "0", "2*pi"]]);
        } else if (kind === "flux") {
            if (sub === "2d") {
                h += field("F_P", "P  (i)", "e.g. x", "x") + field("F_Q", "Q  (j)", "e.g. y", "y");
                h += divider;
                h += field("c_x", "x(t)", "cos(t)", "cos(t)") + field("c_y", "y(t)", "sin(t)", "sin(t)");
                h += bounds([["t", "t:", "0", "2*pi"]]);
            } else {
                h += field("F_P", "P", "e.g. 0", "0") + field("F_Q", "Q", "e.g. 0", "0") + field("F_R", "R", "e.g. 1", "1");
                h += divider;
                h += field("s_x", "x(u, v)", "u*cos(v)", "u*cos(v)") + field("s_y", "y(u, v)", "u*sin(v)", "u*sin(v)") + field("s_z", "z(u, v)", "0", "0");
                h += bounds([["u", "u:", "0", "1"], ["v", "v:", "0", "2*pi"]]);
            }
        }
        form.innerHTML = h;
        const def = document.getElementById("int-definite");
        if (def) def.addEventListener("change", () => {
            document.getElementById("single-bounds").style.display = def.checked ? "" : "none";
        });
    }

    function readBounds() {
        return [...form.querySelectorAll(".bound-row")].map((row) =>
            [row.dataset.var, row.querySelector(".blo").value, row.querySelector(".bhi").value]);
    }

    async function compute() {
        const kind = kindSel.value;
        const p = { kind };
        if (kind === "single") {
            p.integrand = val("f_int");
            const def = document.getElementById("int-definite");
            if (def && def.checked) p.bounds = readBounds();
            else p.var = "x";
        } else if (kind === "double" || kind === "triple") {
            p.coords = coordsSel.value;
            p.integrand = val("f_int");
            p.bounds = readBounds();
        } else if (kind === "line") {
            p.line_mode = subSel.value;
            p.cx = val("c_x"); p.cy = val("c_y"); p.cz = val("c_z");
            p.bounds = readBounds();
            if (subSel.value === "vector") { p.P = val("F_P"); p.Q = val("F_Q"); p.R = val("F_R"); }
            else p.integrand = val("f_int");
        } else if (kind === "flux") {
            if (subSel.value === "2d") {
                p.kind = "flux2d";
                p.P = val("F_P"); p.Q = val("F_Q");
                p.cx = val("c_x"); p.cy = val("c_y");
            } else {
                p.kind = "flux3d";
                p.P = val("F_P"); p.Q = val("F_Q"); p.R = val("F_R");
                p.sx = val("s_x"); p.sy = val("s_y"); p.sz = val("s_z");
            }
            p.bounds = readBounds();
        }

        statusEl.textContent = "Computing\u2026";
        resultEl.textContent = "\u2026"; setupEl.textContent = ""; numericEl.textContent = "";
        try {
            const res = await fetch("/integrate", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(p),
            });
            const d = await res.json();
            if (d.error) { statusEl.textContent = d.error; resultEl.textContent = "\u2014"; return; }
            statusEl.textContent = "";
            if (d.setup_latex) renderTex(setupEl, d.setup_latex);
            if (d.latex) renderTex(resultEl, "= " + d.latex);
            else resultEl.textContent = d.plain || "\u2014";
            numericEl.textContent = (d.numeric !== undefined && d.numeric !== null)
                ? "\u2248 " + Number(d.numeric).toPrecision(8) : "";
        } catch (_) { statusEl.textContent = "Server error."; }
    }

    kindSel.addEventListener("change", refreshSelectors);
    coordsSel.addEventListener("change", renderForm);
    subSel.addEventListener("change", renderForm);
    document.getElementById("int-go").addEventListener("click", compute);
    refreshSelectors();
})();