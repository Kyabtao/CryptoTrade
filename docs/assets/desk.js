/* CryptoTrade dashboard — "GPTHEIST desk" panels.

   Ports the visual grammar of docs/gptheist (caption headers, stat rails,
   return ridgeline, co-fire chord, force graph, penteract, roster strip) onto
   the main site's real bot data, using the same dependency-free SVG approach
   as charts.js. D3 is deliberately NOT used here — every layout (chord
   angles, KDE curves, force simulation, 5-D rotation/projection) is
   implemented locally and deterministically. Math.random is avoided so a
   reload always renders the same picture.

   Palette: SVG presentation attributes do not understand var() reliably in
   browsers, so every draw pass resolves the live CSS custom properties via
   dPalette() — which also lets the cream/dark theme flip re-tint charts by
   simply redrawing them. */

/* ---------- live palette ---------- */

let DP = {};

/* Resolved from the body class — the same source of truth as theme.js
   (siteInk) and charts.js (chartInk), and the values mirror the
   body.theme-cream overrides in style.css. Class-based rather than
   getComputedStyle: deterministic, and SVG attributes cannot use var(). */
function dPalette() {
  const cream = document.body.classList.contains("theme-cream");
  DP = cream
    ? {
        panel: "#ffffff", panel2: "#f3f3ef", borderSoft: "#ebebe6",
        text: "#141414", dim: "#56564f", faint: "#8a8a84",
        accent: "#2f6fed", green: "#1f9d55", red: "#d33333", iso: "#b9b9b1",
      }
    : {
        panel: "#121722", panel2: "#171d2b", borderSoft: "#1c2333",
        text: "#e6eaf2", dim: "#97a1b5", faint: "#5f6b82",
        accent: "#3b82f6", green: "#22c55e", red: "#ef4444", iso: "#414d68",
      };
  return DP;
}

/* ---------- small math helpers (d-prefixed to avoid collisions) ---------- */

function dmean(a) { return a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0; }

function dmedian(a) {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function dquantile(a, q) {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

function dstd(a) {
  if (!a.length) return 0;
  const m = dmean(a);
  return Math.sqrt(dmean(a.map((v) => (v - m) * (v - m))));
}

/* Gaussian-kernel density estimate on a fixed grid (shared x-domain so ticks
   are comparable — the ridge stays honest across frames). */
function dkde(values, x0, x1, steps, bw) {
  const out = [];
  const norm = 1 / (values.length * bw * Math.sqrt(2 * Math.PI));
  for (let s = 0; s <= steps; s++) {
    const x = x0 + ((x1 - x0) * s) / steps;
    let d = 0;
    for (const v of values) {
      const u = (x - v) / bw;
      d += Math.exp(-0.5 * u * u);
    }
    out.push(d * norm);
  }
  return out;
}

/* Silverman bandwidth, guard against zero-variance cross-sections. */
function dsilverman(values) {
  const n = values.length || 1;
  const sd = dstd(values);
  const iqr = dquantile(values, 0.75) - dquantile(values, 0.25);
  const s = Math.min(sd, iqr / 1.349) || sd || 1;
  return Math.max(1e-6, 0.9 * s * Math.pow(n, -0.2));
}

/* Jaccard overlap of two fill-candle sets ("who fires together"). */
function djaccard(a, b) {
  if (!a.size || !b.size) return 0;
  let inter = 0;
  for (const x of a) if (b.has(x)) inter++;
  return inter / (a.size + b.size - inter);
}

/* ---------- shared desk chrome ---------- */

/* A dark tooltip bound to a chart container (container must be position:
   relative — see .dchart in style.css). Returns {show, hide}. */
function dTip(container) {
  const tip = document.createElement("div");
  tip.className = "dtip";
  tip.style.display = "none";
  container.appendChild(tip);
  return {
    show(html, ev) {
      tip.innerHTML = html;
      tip.style.display = "block";
      const r = container.getBoundingClientRect();
      let x = ev.clientX - r.left + 14;
      let y = ev.clientY - r.top + 12;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      if (x + tw > r.width - 4) x = ev.clientX - r.left - tw - 12;
      if (y + th > r.height - 4) y = ev.clientY - r.top - th - 10;
      tip.style.left = x + "px";
      tip.style.top = y + "px";
    },
    hide() { tip.style.display = "none"; },
  };
}

/* Deterministic pseudo-jitter (Math.random is banned in gptheist and skipped
   here too so the graph never re-rolls between renders). */
function dJitter(i, j) {
  return (((i * 31 + j * 17) % 7) - 3) * 0.35;
}

/* ---------- KPI strip (gptheist 4-up cards) ---------- */

/* cards: [{label, unit, value, sub, cls, seg:{share}, dot:'pos'|'neg'}] */
function deskKpis(container, cards) {
  container.innerHTML = cards.map((k) => {
    let seg = "";
    if (k.seg) {
      const on = Math.round(Math.max(0, Math.min(1, k.seg.share)) * 10);
      seg = '<div class="dseg">' +
        Array.from({ length: 10 }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("") +
        "</div>";
    }
    const dot = k.dot ? `<i class="ddot ${k.dot}"></i>` : "";
    return `<div class="card dkpi">
      <div class="dkpi-label">${esc(k.label)} <span>${esc(k.unit || "")}</span>${dot}</div>
      <div class="dkpi-value num ${k.cls || ""}">${k.value}</div>
      ${seg}
      <div class="dkpi-sub">${k.sub || ""}</div>
    </div>`;
  }).join("");
}

/* ---------- balance-history line (green wash · ink line · current tag) ---------- */

/* rows: [{ts, equity}]; opts: {baseline, height} */
function deskEquityChart(container, rows, opts = {}) {
  dPalette();
  const width = chartWidth(container, 800);
  const compact = compactChart(container);
  const height = opts.height || (compact ? 210 : 250);
  const ml = compact ? 46 : 56, mr = compact ? 10 : 40, mt = 16, mb = 22;
  const iw = width - ml - mr, ih = height - mt - mb;
  if (rows.length < 2) {
    container.innerHTML = '<div class="empty">Need at least two recorded ticks.</div>';
    return;
  }
  const vals = rows.map((r) => r.equity);
  let min = Math.min(...vals), max = Math.max(...vals);
  if (opts.baseline != null) { min = Math.min(min, opts.baseline); max = Math.max(max, opts.baseline); }
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.08;
  min -= pad; max += pad;
  const last = rows[rows.length - 1];
  const up = opts.baseline == null ? last.equity >= rows[0].equity : last.equity >= opts.baseline;

  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);
  const x = (i) => ml + (i / (rows.length - 1)) * iw;
  const y = (v) => mt + ih - ((v - min) / (max - min)) * ih;

  // grid + y labels (3 ticks)
  const step = niceStep(max - min, 3);
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) {
    el("line", { x1: ml, x2: ml + iw, y1: y(v), y2: y(v), stroke: DP.borderSoft, "stroke-width": 1 }, svg);
    svgText(ml - 6, y(v) + 3, "$" + Math.round(v).toLocaleString("en-US"), { "text-anchor": "end", "font-size": 9.5, fill: DP.faint, class: "mono" }, svg);
  }
  // baseline (funded capital) as dashed reference
  if (opts.baseline != null && opts.baseline > min && opts.baseline < max) {
    el("line", { x1: ml, x2: ml + iw, y1: y(opts.baseline), y2: y(opts.baseline), stroke: DP.faint, "stroke-dasharray": "3 4", "stroke-width": 1 }, svg);
    svgText(ml + iw + 4, y(opts.baseline) + 3, "BASE", { "font-size": 8.5, fill: DP.faint, class: "mono" }, svg);
  }
  // x labels: first / mid / last
  const xlab = [0, Math.floor((rows.length - 1) / 2), rows.length - 1];
  xlab.forEach((i) => {
    svgText(x(i), height - 6, fmtTsShort(rows[i].ts), { "text-anchor": i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle", "font-size": 9.5, fill: DP.faint, class: "mono" }, svg);
  });

  // green/red wash under the line, then the ink line
  const linePts = rows.map((r, i) => `${x(i).toFixed(1)},${y(r.equity).toFixed(1)}`).join(" L ");
  el("path", {
    d: `M ${x(0)},${mt + ih} L ${linePts} L ${x(rows.length - 1)},${mt + ih} Z`,
    fill: up ? "rgba(34,197,94,0.13)" : "rgba(239,68,68,0.12)",
  }, svg);
  el("path", { d: `M ${linePts}`, fill: "none", stroke: DP.text, "stroke-width": 1.7, "stroke-linejoin": "round" }, svg);

  // current point: red dot + tag (the gptheist signature)
  const cx = x(rows.length - 1), cy = y(last.equity);
  el("circle", { cx, cy, r: 3.4, fill: DP.red, stroke: DP.panel, "stroke-width": 1.4 }, svg);
  const tag = "$" + Math.round(last.equity).toLocaleString("en-US");
  const tw = tag.length * 6.2 + 12;
  const tx = Math.min(cx - tw + 6, ml + iw - tw);
  const ty = Math.max(cy - 26, mt - 4);
  el("rect", { x: tx, y: ty, width: tw, height: 17, rx: 3.5, fill: DP.panel2, stroke: DP.red, "stroke-width": 1 }, svg);
  svgText(tx + tw / 2, ty + 12, tag, { "text-anchor": "middle", "font-size": 10, fill: DP.text, class: "mono" }, svg);

  // crosshair hover
  const tip = dTip(container);
  const cross = el("line", { y1: mt, y2: mt + ih, stroke: DP.faint, "stroke-dasharray": "3 3", visibility: "hidden" }, svg);
  const hdot = el("circle", { r: 3, fill: DP.text, visibility: "hidden" }, svg);
  const hit = el("rect", { x: ml, y: mt, width: iw, height: ih, fill: "transparent" }, svg);
  hit.addEventListener("mousemove", (ev) => {
    const r = container.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * width;
    const i = Math.max(0, Math.min(rows.length - 1, Math.round(((px - ml) / iw) * (rows.length - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
    cross.setAttribute("visibility", "visible");
    hdot.setAttribute("cx", x(i)); hdot.setAttribute("cy", y(rows[i].equity));
    hdot.setAttribute("visibility", "visible");
    const base = opts.baseline != null ? opts.baseline : rows[0].equity;
    const d = rows[i].equity - base;
    tip.show(
      `<b>${esc(fmtTsShort(rows[i].ts))}</b><span class="num"> ${fmtUSD(rows[i].equity)}</span><br>` +
      `<span class="${pctClass(d)} num">${fmtUSD(d)}</span> vs base`,
      ev
    );
  });
  hit.addEventListener("mouseleave", () => {
    cross.setAttribute("visibility", "hidden");
    hdot.setAttribute("visibility", "hidden");
    tip.hide();
  });
}

/* ---------- activity log ---------- */

function dLogRow(e) {
  return `
    <div class="dlog-row">
      <span class="dlog-t num">${esc(e.ts)}</span>
      <span class="dlog-code mono" style="color:${e.color};border-color:${e.color}44">${esc(e.code)}</span>
      <span class="dlog-body">
        <b>${esc(e.name)}</b>
        <span class="dlog-msg">${esc(e.msg || "")}</span>
      </span>
      <span class="dlog-right num ${e.rightCls || ""}">${e.right || ""}</span>
    </div>`;
}

/* entries: [{ts, code, color, name, msg, right, rightCls}] — newest first.
   The gptheist reference pins the newest event in a spotlight block (big time
   + code, message on the second line) above the scrolling list. */
function deskActivityLog(container, entries, cap = 70) {
  if (!entries.length) {
    container.innerHTML = '<div class="empty">No fills recorded yet.</div>';
    return;
  }
  const s = entries[0];
  const side = s.side || "";
  container.innerHTML = `
    <div class="dlog-spot">
      <div class="dlog-spot-top">
        <span class="dlog-spot-t num">${esc(s.ts)}</span>
        <span class="dlog-code mono" style="color:${s.color};border-color:${s.color}44">${esc(s.code)}</span>
        <b class="dlog-spot-name">${esc(s.name)}</b>
        <span class="dlog-spot-right num ${s.rightCls || ""}">${s.right || ""}</span>
      </div>
      <div class="dlog-spot-msg">${esc(side ? side.toUpperCase() + " · " : "")}${esc(s.msg || "")}</div>
    </div>
    <div class="dlog-list">${entries.slice(1, cap).map(dLogRow).join("")}</div>`;
}

/* ---------- return ridgeline ---------- */

/* frames: [{ts, values:[…]}] oldest → newest; one KDE curve per tick drawn as
   a diagonally offset ridgeline (back = oldest at the top, newest in front).
   The 0% line is the "strike": the profitable side of the newest curve is
   shaded green, the losing side red. */
function deskRidge(container, frames, opts = {}) {
  dPalette();
  const width = chartWidth(container, 980);
  const compact = compactChart(container);
  const height = opts.height || (compact ? 300 : 340);
  const ml = compact ? 40 : 52, mr = compact ? 8 : 18, mt = 14, mb = 22;
  const iw = width - ml - mr, ih = height - mt - mb;
  if (frames.length < 3) {
    container.innerHTML = '<div class="empty">Need at least three ticks for the ridge.</div>';
    return;
  }
  const all = frames.flatMap((f) => f.values);
  let x0 = Math.min(...all), x1 = Math.max(...all);
  const padX = Math.max(0.5, (x1 - x0) * 0.12);
  x0 = Math.min(x0, 0) - padX; x1 = Math.max(x1, 0) + padX;
  const bw = dsilverman(all);
  const steps = 70;
  const n = frames.length;
  const dy = (ih * 0.86) / n;
  const amp = dy * 2.4;
  const dxo = (iw * 0.26) / Math.max(1, n - 1);
  const curves = frames.map((f) => dkde(f.values, x0, x1, steps, bw));
  const maxD = Math.max(...curves.flat());

  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);
  const X = (v, off) => ml + ((v - x0) / (x1 - x0)) * iw + off;
  const zeroX = X(0, 0);

  // per-frame baseline y (frame i: 0 = oldest = top … n-1 = newest = bottom)
  const baseY = (i) => mt + dy * 0.8 + i * dy;

  const curvePts = (c, i) =>
    c.map((d, s) => `${X(x0 + ((x1 - x0) * s) / steps, i * dxo).toFixed(1)},${(baseY(i) - (d / maxD) * amp).toFixed(1)}`).join(" L ");

  // x-axis labels
  const xTick = (v, anchor) => svgText(X(v, 0), height - 6, (v > 0 ? "+" : "") + v.toFixed(1) + "%", { "text-anchor": anchor, "font-size": 9.5, fill: DP.faint, class: "mono" }, svg);
  xTick(Math.round((x0 + padX) * 10) / 10, "start");
  xTick(0, "middle");
  xTick(Math.round((x1 - padX) * 10) / 10, "end");

  // dashed 0% "strike" through the whole surface
  el("line", { x1: zeroX, x2: zeroX, y1: mt, y2: baseY(n - 1) + 6, stroke: DP.red, "stroke-dasharray": "4 4", "stroke-width": 1, opacity: 0.55 }, svg);

  // draw back → front so nearer ridges occlude the ones behind
  const groups = curves.map((c, i) => {
    const g = el("g", { class: "dridge-g" }, svg);
    const occl = `M ${curvePts(c, i)} L ${X(x1, i * dxo)},${baseY(i)} L ${X(x0, i * dxo)},${baseY(i)} Z`;
    el("path", { d: occl, fill: DP.panel }, g);
    return { g, i };
  });

  // newest curve: shade profit / loss side, brighter stroke
  const li = n - 1;
  const lc = curves[li];
  const profPts = [], lossPts = [];
  lc.forEach((d, s) => {
    const vx = x0 + ((x1 - x0) * s) / steps;
    const px = X(vx, li * dxo), py = baseY(li) - (d / maxD) * amp;
    (vx >= 0 ? profPts : lossPts).push(`${px.toFixed(1)},${py.toFixed(1)}`);
  });
  if (lossPts.length > 1) {
    el("path", { d: `M ${lossPts.join(" L ")} L ${X(x0, li * dxo).toFixed(1)},${baseY(li)} Z`, fill: "rgba(239,68,68,0.16)" }, svg);
  }
  if (profPts.length > 1) {
    const first = profPts[0].split(",")[0];
    el("path", { d: `M ${profPts.join(" L ")} L ${X(x1, li * dxo).toFixed(1)},${baseY(li)} L ${first},${baseY(li)} Z`, fill: "rgba(34,197,94,0.18)" }, svg);
  }

  // strokes on top (muted for history, ink for the newest)
  groups.forEach(({ g, i }) => {
    el("path", {
      d: `M ${curvePts(curves[i], i)}`, fill: "none",
      stroke: i === n - 1 ? DP.text : DP.dim,
      "stroke-width": i === n - 1 ? 1.8 : 1, opacity: i === n - 1 ? 1 : 0.55,
    }, g);
  });
  svgText(ml + iw + 4, baseY(n - 1) + 3, "NOW", { "font-size": 8.5, fill: DP.faint, class: "mono" }, svg);

  // hover: pick the frame under the pointer, highlight it, show its stats
  const tip = dTip(container);
  const hoverPath = el("path", { fill: "none", stroke: DP.accent, "stroke-width": 1.6, visibility: "hidden", "pointer-events": "none" }, svg);
  const hit = el("rect", { x: 0, y: 0, width, height, fill: "transparent" }, svg);
  hit.addEventListener("mousemove", (ev) => {
    const r = container.getBoundingClientRect();
    const py = ((ev.clientY - r.top) / r.height) * height;
    const i = Math.max(0, Math.min(n - 1, Math.round((py - mt - dy * 0.8) / dy)));
    hoverPath.setAttribute("d", `M ${curvePts(curves[i], i)}`);
    hoverPath.setAttribute("visibility", "visible");
    const f = frames[i], med = dmedian(f.values), pos = f.values.filter((v) => v > 0).length;
    tip.show(
      `<b>TICK ${esc(fmtTsShort(f.ts))}</b><br>` +
      `median <span class="num ${pctClass(med)}">${fmtPct(med)}</span> · ` +
      `<span class="num">${pos}/${f.values.length}</span> in profit<br>` +
      `<span class="num">${fmtPct(Math.max(...f.values))} best · ${fmtPct(Math.min(...f.values))} worst</span>`,
      ev
    );
  });
  hit.addEventListener("mouseleave", () => {
    hoverPath.setAttribute("visibility", "hidden");
    tip.hide();
  });
}

/* ---------- chord diagram ---------- */

/* Standard chord layout implemented locally: group arcs proportional to row
   sums, ribbon sub-arcs per matrix cell. matrix must be non-negative. */
function dChordLayout(matrix, pad = 0.06) {
  const n = matrix.length;
  const sums = matrix.map((r) => r.reduce((a, b) => a + b, 0));
  const total = sums.reduce((a, b) => a + b, 0) || 1;
  const k = (2 * Math.PI - n * pad) / total;
  let a = -Math.PI / 2;
  const groups = [], subs = [];
  for (let i = 0; i < n; i++) {
    const start = a;
    const sub = [];
    for (let j = 0; j < n; j++) {
      const v = matrix[i][j] * k;
      sub.push([a, a + v]);
      a += v;
    }
    groups.push({ start, end: a, sum: sums[i] });
    subs.push(sub);
    a += pad;
  }
  return { groups, subs, total };
}

const dP = (a, r) => (r * Math.sin(a)).toFixed(2) + "," + (-r * Math.cos(a)).toFixed(2);

function dRibbonPath(s0, s1, t0, t1, r) {
  return `M${dP(s0, r)} A${r},${r} 0 0 1 ${dP(s1, r)} Q0,0 ${dP(t0, r)} A${r},${r} 0 0 1 ${dP(t1, r)} Q0,0 ${dP(s0, r)}Z`;
}

function dArcPath(a0, a1, r0, r1) {
  const big = a1 - a0 > Math.PI ? 1 : 0;
  return `M${dP(a0, r1)} A${r1},${r1} 0 ${big} 1 ${dP(a1, r1)} L${dP(a1, r0)} A${r0},${r0} 0 ${big} 0 ${dP(a0, r0)}Z`;
}

/* matrix: n×n non-negative; labels/colors per group. Hover an arc to isolate
   its ribbons; hover a ribbon for the pair's strength. */
function deskChord(container, matrix, labels, colors, opts = {}) {
  const width = chartWidth(container, 460);
  const height = opts.height || Math.max(300, Math.min(380, width * 0.82));
  const { groups, subs, total } = dChordLayout(matrix);
  const n = matrix.length;
  const cx = width / 2, cy = height / 2;
  const R = Math.min(width, height) / 2 - 34;
  const r0 = R - 16, r1 = R, rr = R - 2;
  const maxV = Math.max(...matrix.flat()) || 1;

  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", "aria-label": "Co-fire chord between strategy categories" }, container);
  const gAll = el("g", { transform: `translate(${cx},${cy})` }, svg);
  const gRibbons = el("g", {}, gAll);
  const gArcs = el("g", {}, gAll);
  const tip = dTip(container);

  const ribbons = [];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const v = matrix[i][j];
      if (v <= 0) continue;
      const p = el("path", {
        d: dRibbonPath(subs[i][j][0], subs[i][j][1], subs[j][i][0], subs[j][i][1], rr),
        fill: "#3b82f6", opacity: 0.08 + 0.38 * (v / maxV), class: "dribbon",
      }, gRibbons);
      p.__pair = { i, j, v };
      ribbons.push(p);
    }
  }

  const arcEls = groups.map((g, i) => {
    const p = el("path", { d: dArcPath(g.start, g.end, r0, r1), fill: colors[i], class: "darc" }, gArcs);
    const mid = (g.start + g.end) / 2;
    const lr = R + 12;
    const anchor = Math.sin(mid) > 0.08 ? "start" : Math.sin(mid) < -0.08 ? "end" : "middle";
    svgText(lr * Math.sin(mid), -lr * Math.cos(mid) + 3, labels[i], {
      "text-anchor": anchor, "font-size": 8.5, fill: colors[i], class: "mono", "letter-spacing": "0.5",
    }, gArcs);
    p.__idx = i;
    return p;
  });

  const dimOthers = (keep) => {
    ribbons.forEach((r) => {
      const hit = !keep || r.__pair.i === keep || r.__pair.j === keep;
      r.setAttribute("opacity", keep ? (hit ? 0.55 : 0.04) : r.getAttribute("opacity"));
    });
  };
  arcEls.forEach((p) => {
    p.addEventListener("mouseenter", (ev) => {
      dimOthers(p.__idx);
      const g = groups[p.__idx];
      tip.show(`<b>${esc(labels[p.__idx])}</b><br><span class="num">${((g.sum / total) * 100).toFixed(1)}%</span> of all co-fire strength`, ev);
    });
    p.addEventListener("mouseleave", () => { dimOthers(null); tip.hide(); });
  });
  ribbons.forEach((r) => {
    r.addEventListener("mouseenter", (ev) => {
      dimOthers(-1);
      r.setAttribute("opacity", 0.75);
      tip.show(`<b>${esc(labels[r.__pair.i])}</b> ↔ <b>${esc(labels[r.__pair.j])}</b><br>mean co-fire <span class="num">${r.__pair.v.toFixed(3)}</span>`, ev);
    });
    r.addEventListener("mouseleave", () => { dimOthers(null); tip.hide(); });
  });
}

/* ---------- return distribution histogram ---------- */

function deskHistogram(container, values, opts = {}) {
  dPalette();
  const width = chartWidth(container, 460);
  const height = opts.height || 220;
  const ml = 36, mr = 10, mt = 12, mb = 22;
  const iw = width - ml - mr, ih = height - mt - mb;
  if (!values.length) { container.innerHTML = '<div class="empty">No data.</div>'; return; }
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const nBins = 14;
  const bw = span / nBins;
  const bins = Array.from({ length: nBins }, (_, i) => ({ x0: min + i * bw, x1: min + (i + 1) * bw, n: 0 }));
  values.forEach((v) => {
    let b = Math.floor((v - min) / bw);
    if (b >= nBins) b = nBins - 1;
    bins[b].n++;
  });
  const maxN = Math.max(...bins.map((b) => b.n));
  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);
  const x = (v) => ml + ((v - min) / span) * iw;
  const y = (c) => mt + ih - (c / maxN) * ih;

  const tip = dTip(container);
  bins.forEach((b) => {
    const mid = (b.x0 + b.x1) / 2;
    const t = Math.abs(mid) / (Math.abs(mid) > 0 ? Math.max(Math.abs(min), Math.abs(max)) : 1);
    const fill = mid >= 0
      ? `rgba(34,197,94,${(0.30 + 0.55 * t).toFixed(2)})`
      : `rgba(239,68,68,${(0.30 + 0.55 * t).toFixed(2)})`;
    const bar = el("rect", {
      x: x(b.x0) + 1, y: y(b.n), width: Math.max(1, x(b.x1) - x(b.x0) - 2),
      height: mt + ih - y(b.n), fill, rx: 2,
    }, svg);
    bar.addEventListener("mouseenter", (ev) => tip.show(`<span class="num">${fmtPct(b.x0, 1)} … ${fmtPct(b.x1, 1)}</span><br><b class="num">${b.n}</b> strategies`, ev));
    bar.addEventListener("mouseleave", () => tip.hide());
  });
  // zero line
  if (min < 0 && max > 0) {
    el("line", { x1: x(0), x2: x(0), y1: mt, y2: mt + ih, stroke: DP.faint, "stroke-dasharray": "3 3" }, svg);
    svgText(x(0), height - 6, "0%", { "text-anchor": "middle", "font-size": 9.5, fill: DP.faint, class: "mono" }, svg);
  }
  svgText(ml, height - 6, fmtPct(min, 1), { "font-size": 9.5, fill: DP.faint, class: "mono" }, svg);
  svgText(ml + iw, height - 6, fmtPct(max, 1), { "text-anchor": "end", "font-size": 9.5, fill: DP.faint, class: "mono" }, svg);
}

/* ---------- signal graph (force-directed co-fire web) ---------- */

/* Deterministic force simulation: repulsion + springs + gravity. Positions
   are stored on the nodes, so filtering links (threshold slider) redraws
   without re-simulating. */
function dForceSim(nodes, links, width, height, iterations = 420) {
  const R = Math.min(width, height) * 0.34;
  nodes.forEach((nd, i) => {
    if (nd.x == null) {
      const a = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
      nd.x = width / 2 + R * Math.cos(a) + dJitter(i, 3);
      nd.y = height / 2 + R * Math.sin(a) + dJitter(5, i);
    }
    nd.vx = 0; nd.vy = 0;
  });
  const rep = 3400, spring = 0.03, rest = 46, grav = 0.02, damp = 0.85;
  for (let it = 0; it < iterations; it++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 4) { dx += dJitter(i, j); dy += dJitter(j, i); d2 = dx * dx + dy * dy + 4; }
        const f = Math.min(6, rep / (d2 + 120));
        const d = Math.sqrt(d2), ux = dx / d, uy = dy / d;
        a.vx -= ux * f; a.vy -= uy * f;
        b.vx += ux * f; b.vy += uy * f;
      }
    }
    for (const l of links) {
      const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = spring * (d - rest) * (0.7 + l.v);
      const ux = dx / d, uy = dy / d;
      l.s.vx += ux * f; l.s.vy += uy * f;
      l.t.vx -= ux * f; l.t.vy -= uy * f;
    }
    for (const nd of nodes) {
      nd.vx += (width / 2 - nd.x) * grav;
      nd.vy += (height / 2 - nd.y) * grav;
      nd.vx *= damp; nd.vy *= damp;
      nd.x += nd.vx; nd.y += nd.vy;
    }
  }
  // normalize into the box
  const pad = 40;
  const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const s = Math.min((width - 2 * pad) / Math.max(1, x1 - x0), (height - 2 * pad) / Math.max(1, y1 - y0), 1.8);
  nodes.forEach((nd) => {
    nd.x = pad + (nd.x - x0) * s + (width - 2 * pad - (x1 - x0) * s) / 2;
    nd.y = pad + (nd.y - y0) * s + (height - 2 * pad - (y1 - y0) * s) / 2;
  });
}

/* nodes: [{id,name,cat,color,ret,fills,x,y,r}], links: [{s,t,v}] (v 0..1).
   opts: {height, labelMinDegree, onStatus}. Clicking a node opens its lesson. */
function deskSignalGraph(container, nodes, links, opts = {}) {
  dPalette();
  const width = chartWidth(container, 980);
  const height = opts.height || (compactChart(container) ? 360 : 430);
  if (!nodes.simulated) dForceSim(nodes, links, width, height);
  nodes.simulated = true;

  // neighbour map for hover highlighting
  const nbr = new Map(nodes.map((n) => [n, []]));
  links.forEach((l) => { nbr.get(l.s).push(l); nbr.get(l.t).push(l); });
  const deg = new Map(nodes.map((n) => [n, nbr.get(n).length]));

  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", "aria-label": "Co-fire signal graph of the 42 strategies" }, container);
  const tip = dTip(container);
  const gE = el("g", {}, svg), gN = el("g", {}, svg);

  const edgeEls = links.map((l) => {
    const line = el("line", {
      x1: l.s.x, y1: l.s.y, x2: l.t.x, y2: l.t.y,
      stroke: "#3b82f6", "stroke-width": 0.7 + l.v * 2.4, opacity: 0.14 + l.v * 0.4,
    }, gE);
    line.__l = l;
    return line;
  });

  const labelMin = opts.labelMinDegree != null ? opts.labelMinDegree : 3;
  const nodeEls = nodes.map((nd) => {
    const iso = deg.get(nd) === 0;
    const c = el("circle", {
      cx: nd.x, cy: nd.y, r: iso ? 3.5 : nd.r,
      fill: iso ? "none" : nd.color, stroke: iso ? DP.iso : DP.panel,
      "stroke-width": iso ? 1.2 : 1.4, opacity: iso ? 0.6 : 1, class: "dnode",
    }, gN);
    c.__n = nd;
    if (deg.get(nd) >= labelMin && !iso) {
      svgText(nd.x, nd.y - nd.r - 5, nd.name.length > 16 ? nd.name.slice(0, 15) + "…" : nd.name, {
        "text-anchor": "middle", "font-size": 8.5, fill: DP.faint, class: "mono",
      }, gN).__owner = c;
    }
    return c;
  });

  const focus = (nd) => {
    const keep = new Set([nd]);
    nbr.get(nd).forEach((l) => { keep.add(l.s); keep.add(l.t); });
    edgeEls.forEach((e) => {
      const on = e.__l.s === nd || e.__l.t === nd;
      e.setAttribute("opacity", on ? 0.85 : 0.05);
    });
    nodeEls.forEach((c) => c.setAttribute("opacity", keep.has(c.__n) ? 1 : 0.15));
  };
  const blur = () => {
    edgeEls.forEach((e) => { e.setAttribute("opacity", 0.14 + e.__l.v * 0.4); });
    nodeEls.forEach((c) => c.setAttribute("opacity", deg.get(c.__n) === 0 ? 0.6 : 1));
  };

  nodeEls.forEach((c) => {
    const nd = c.__n;
    c.addEventListener("mouseenter", (ev) => {
      c.setAttribute("r", (deg.get(nd) === 0 ? 3.5 : nd.r) + 2.5);
      focus(nd);
      tip.show(
        `<b>${esc(nd.name)}</b><br><span style="color:${nd.color}">${esc(nd.cat)}</span><br>` +
        `fills <span class="num">${nd.fills}</span> · return <span class="num ${pctClass(nd.ret)}">${fmtPct(nd.ret)}</span><br>` +
        `co-fire links <span class="num">${deg.get(nd)}</span>`,
        ev
      );
      if (opts.onStatus) opts.onStatus(nd);
    });
    c.addEventListener("mouseleave", () => {
      c.setAttribute("r", deg.get(nd) === 0 ? 3.5 : nd.r);
      blur(); tip.hide();
      if (opts.onStatus) opts.onStatus(null);
    });
    c.addEventListener("click", () => { window.location.href = "lesson.html?id=" + encodeURIComponent(nd.id); });
  });
}

/* ---------- 5-D metric lattice (penteract of the strategy fleet) ---------- */

/* Every strategy is projected onto a 5-dimensional hypercube: each axis is a
   real metric (return, activity, win rate, exposure, fee efficiency), each
   bit is above/below the fleet median, so the 42 books scatter across the 32
   vertices of a penteract. Edges are coloured by the axis they flip; the
   wireframe rotates through two 5-D planes and projects 5D → 2D. */

function dBitsKey(bits) {
  let k = 0;
  bits.forEach((b, i) => { if (b) k |= 1 << i; });
  return k;
}

function dRot5(p, a, b) {
  const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b);
  const [x, y, z, w, v] = p;
  return [x * ca - w * sa, y * cb - v * sb, z, x * sa + w * ca, y * sb + v * cb];
}

/* iterative perspective 5D → 4D → 3D → 2D; returns [px, py, depth] where
   depth is the last projection scale (bigger = closer to the viewer). */
function dProject5(p) {
  const D = 2.6;
  let [x, y, z, w, v] = p;
  let s = 1 / (D - v);
  x *= s; y *= s; z *= s; w *= s;
  s = 1 / (D - w);
  x *= s; y *= s; z *= s;
  s = 1 / (D - z);
  return [x * s, y * s, s];
}

/* items: [{name, bits:[0|1 ×5], ret, color}]; opts: {height, axes:[{label,color}×5],
   onFrame(deg), reduced}. Vertices show occupancy; hover a vertex for the
   books that land on it. */
function deskLattice(container, items, opts = {}) {
  dPalette();
  const width = chartWidth(container, 620);
  const height = opts.height || Math.max(320, Math.min(460, Math.round(width * 0.9)));
  const V = 32;

  const occ = Array.from({ length: V }, () => []);
  items.forEach((it) => occ[dBitsKey(it.bits)].push(it));

  // unit penteract: 32 vertices ±1^5, 80 edges (flip exactly one bit)
  const coords = [];
  for (let k = 0; k < V; k++) {
    coords.push([k & 1, (k >> 1) & 1, (k >> 2) & 1, (k >> 3) & 1, (k >> 4) & 1].map((b) => (b ? 1 : -1)));
  }
  const edges = [];
  for (let k = 0; k < V; k++) {
    for (let d = 0; d < 5; d++) {
      const m = k ^ (1 << d);
      if (m > k) edges.push({ k, m, d });
    }
  }
  const AXCOL = (opts.axes || []).map((a) => a.color);
  const axColor = (d) => AXCOL[d % Math.max(1, AXCOL.length)] || "#3b82f6";

  const R = Math.min(width, height) / 2 - 26;
  const cx = width / 2, cy = height / 2;
  let a = 0.62, b = 0.94;
  const reduced = opts.reduced ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  container.innerHTML = "";
  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`, class: "chart",
    "aria-label": "Five-dimensional metric lattice of the 42 strategies, rotating penteract wireframe",
  }, container);
  const tip = dTip(container);
  const gE = el("g", {}, svg), gV = el("g", {}, svg);

  const edgeEls = edges.map((e) =>
    el("line", { stroke: axColor(e.d), "stroke-width": 1, opacity: 0.4 }, gE)
  );

  const vertEls = coords.map((_, k) => {
    const c = el("circle", { r: 3, class: "dnode" }, gV);
    c.__k = k;
    return c;
  });

  function render() {
    // rotate + project every vertex, then auto-fit into the box
    const proj = coords.map((p) => dProject5(dRot5(p, a, b)));
    let m = 0, sMin = Infinity, sMax = -Infinity;
    proj.forEach(([px, py, s]) => {
      m = Math.max(m, Math.abs(px), Math.abs(py));
      sMin = Math.min(sMin, s); sMax = Math.max(sMax, s);
    });
    const k = (R * 0.94) / (m || 1);
    const span = Math.max(1e-9, sMax - sMin);
    const pos = proj.map(([px, py, s]) => ({
      x: cx + px * k, y: cy - py * k,
      depth: (s - sMin) / span, // 0 = far … 1 = near
    }));

    edges.forEach((e, i) => {
      const A = pos[e.k], B = pos[e.m];
      const el2 = edgeEls[i];
      el2.setAttribute("x1", A.x.toFixed(1)); el2.setAttribute("y1", A.y.toFixed(1));
      el2.setAttribute("x2", B.x.toFixed(1)); el2.setAttribute("y2", B.y.toFixed(1));
      el2.setAttribute("opacity", (0.16 + 0.5 * ((A.depth + B.depth) / 2)).toFixed(2));
    });

    vertEls.forEach((c) => {
      const g = occ[c.__k], P = pos[c.__k];
      c.setAttribute("cx", P.x.toFixed(1)); c.setAttribute("cy", P.y.toFixed(1));
      if (g.length) {
        const avg = g.reduce((s2, it) => s2 + it.ret, 0) / g.length;
        c.setAttribute("r", (3.5 + Math.min(4.5, Math.sqrt(g.length) * 1.6)).toFixed(1));
        c.setAttribute("fill", avg >= 0 ? DP.green : DP.red);
        c.setAttribute("stroke", DP.panel);
        c.setAttribute("stroke-width", "1.2");
        c.setAttribute("opacity", (0.55 + 0.45 * P.depth).toFixed(2));
        c.__info = `${g.length} BOOK${g.length > 1 ? "S" : ""} HERE<br>` +
          g.slice(0, 5).map((it) => `<b>${esc(chartLabel(it.name, 22))}</b> <span class="num ${pctClass(it.ret)}">${fmtPct(it.ret)}</span>`).join("<br>") +
          (g.length > 5 ? `<br>… +${g.length - 5} more` : "") +
          `<br>vertex avg <span class="num ${pctClass(avg)}">${fmtPct(avg)}</span>`;
      } else {
        c.setAttribute("r", "2.6");
        c.setAttribute("fill", "none");
        c.setAttribute("stroke", DP.iso);
        c.setAttribute("stroke-width", "1");
        c.setAttribute("opacity", "0.5");
        c.__info = "NO BOOK LANDS HERE";
      }
    });

    if (opts.onFrame) {
      const deg = Math.round(((a * 180) / Math.PI) % 360);
      opts.onFrame(deg < 0 ? deg + 360 : deg);
    }
  }

  vertEls.forEach((c) => {
    c.addEventListener("mouseenter", (ev) => tip.show(c.__info || "", ev));
    c.addEventListener("mouseleave", () => tip.hide());
  });

  render();
  if (!reduced) {
    /* token-guarded loop: redrawing the container (theme flip, resize)
       supersedes the previous animation instead of stacking loops */
    const token = (container.__latToken = {});
    const step = () => {
      if (container.__latToken !== token) return; // a newer draw took over
      a += 0.0042; b += 0.0026;
      render();
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}

/* ---------- roster strip (crew cards) ---------- */

/* cards: [{idx, name, id, cat, color, ret, spark:[…], href}] */
function deskRoster(container, cards) {
  container.innerHTML = cards.map((c) => {
    const initials = c.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
    const spark = c.spark && c.spark.length > 1 ? dSpark(c.spark, c.color) : "";
    const dot = c.ret >= 0 ? "pos" : "neg";
    return `<a class="dcrew" href="${esc(c.href)}">
      <span class="dcrew-idx num">${esc(c.idx)}</span>
      <i class="ddot ${dot}"></i>
      <span class="dcrew-avatar" style="color:${c.color};background:${c.color}1c;border-color:${c.color}55">${esc(initials)}</span>
      ${spark ? `<span class="dcrew-spark">${spark}</span>` : ""}
      <b class="dcrew-name">${esc(c.name)}</b>
      <span class="dcrew-role" style="color:${c.color}">${esc(c.cat)}</span>
      <span class="dcrew-ret num ${pctClass(c.ret)}">${fmtPct(c.ret)}</span>
    </a>`;
  }).join("");
}

/* tiny inline sparkline (cumulative-return series) */
function dSpark(values, color) {
  const w = 92, h = 24, pad = 2;
  let min = Math.min(...values, 0), max = Math.max(...values, 0);
  if (min === max) { min -= 0.1; max += 0.1; }
  const x = (i) => pad + (i / (values.length - 1)) * (w - 2 * pad);
  const y = (v) => pad + (1 - (v - min) / (max - min)) * (h - 2 * pad);
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const zero = (min < 0 && max > 0)
    ? `<line x1="${pad}" x2="${w - pad}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}" stroke="rgba(128,128,128,.5)" stroke-width="0.5"/>` : "";
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">${zero}` +
    `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.3" stroke-linejoin="round"/></svg>`;
}
