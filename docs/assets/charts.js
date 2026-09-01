/* CryptoTrade dashboard — dependency-free SVG charts. */

const SVGNS = "http://www.w3.org/2000/svg";

function el(name, attrs, parent) {
  const node = document.createElementNS(SVGNS, name);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(node);
  return node;
}

function svgText(x, y, text, attrs, parent) {
  const t = el("text", Object.assign({ x, y }, attrs), parent);
  t.textContent = text;
  return t;
}

function niceStep(span, target) {
  const rough = span / target;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  let step;
  if (norm <= 1) step = 1;
  else if (norm <= 2) step = 2;
  else if (norm <= 5) step = 5;
  else step = 10;
  return step * mag;
}

/* Line chart. `series` = [{name, color, values:[...], area?}], `labels` = x labels. */
function lineChart(container, series, labels, opts = {}) {
  const width = container.clientWidth || 800;
  const height = opts.height || 260;
  const ml = opts.ml || 58, mr = 14, mt = 14, mb = 26;
  const iw = width - ml - mr, ih = height - mt - mb;

  let all = [];
  series.forEach((s) => (all = all.concat(s.values.filter((v) => v != null))));
  if (!all.length) { container.innerHTML = '<div class="empty">No history yet</div>'; return; }
  let min = Math.min(...all), max = Math.max(...all);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.06;
  min -= pad; max += pad;
  const n = series[0].values.length;

  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);

  const x = (i) => ml + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v) => mt + ih - ((v - min) / (max - min)) * ih;

  // gridlines + y labels
  const step = niceStep(max - min, 5);
  const y0 = Math.ceil(min / step) * step;
  for (let g = y0; g <= max; g += step) {
    el("line", { x1: ml, x2: ml + iw, y1: y(g), y2: y(g), stroke: "#1c2333", "stroke-width": 1 }, svg);
    svgText(ml - 8, y(g) + 4, (opts.yFmt || ((v) => v.toLocaleString("en-US", { maximumFractionDigits: 2 })))(g),
      { "text-anchor": "end", "font-size": 11, fill: "#5f6b82", class: "num" }, svg);
  }

  // x labels
  const ticks = opts.ticks || 6;
  const every = Math.max(1, Math.ceil(n / ticks));
  for (let i = 0; i < n; i += every) {
    svgText(x(i), height - 7, (opts.xFmt || ((i) => labels[i] || ""))(i),
      { "text-anchor": "middle", "font-size": 11, fill: "#5f6b82", class: "num" }, svg);
  }

  series.forEach((s) => {
    if (!s.values.length) return;
    const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)]));
    const valid = pts.filter(Boolean);
    if (!valid.length) return;

    if (s.area) {
      el("path", {
        d: "M" + valid.map((p) => p.join(",")).join(" L") + ` L${x(n - 1)},${mt + ih} L${x(0)},${mt + ih} Z`,
        fill: s.fill || "rgba(59,130,246,0.12)",
        stroke: "none",
      }, svg);
    }
    el("path", {
      d: "M" + valid.map((p) => p.join(",")).join(" L"),
      fill: "none", stroke: s.color || "#3b82f6", "stroke-width": opts.stroke || 2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
    }, svg);

    if (n <= 80) {
      valid.forEach((p, i) => {
        const c = el("circle", { cx: p[0], cy: p[1], r: 2.4, fill: s.color || "#3b82f6" }, svg);
        const title = el("title", {}, c);
        title.textContent = `${s.name}: ${(opts.tipFmt || ((v) => v))(s.values[i])}`;
      });
    }
  });
}

/* Divergent horizontal bar chart (centre at zero). `items` = [{label, value, color}]. */
function barChartH(container, items, opts = {}) {
  const width = container.clientWidth || 800;
  const rowH = opts.rowH || 20;
  const gap = opts.gap || 6;
  const height = Math.max(40, items.length * (rowH + gap) + 8);
  const labelW = opts.labelW || 210;
  const chartX = labelW + 10, chartW = width - chartX - 58;
  const maxAbs = Math.max(1, ...items.map((i) => Math.abs(i.value)));

  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);

  const zeroX = chartX + chartW / 2;
  el("line", { x1: zeroX, x2: zeroX, y1: 0, y2: height, stroke: "#2a3348", "stroke-width": 1 }, svg);

  items.forEach((item, i) => {
    const cy = i * (rowH + gap) + rowH / 2 + 2;
    svgText(labelW, cy + 4, item.label, { "text-anchor": "end", "font-size": 11.5, fill: "#97a1b5" }, svg);
    const w = (Math.abs(item.value) / maxAbs) * (chartW / 2);
    const bx = item.value >= 0 ? zeroX + 2 : zeroX - 2 - w;
    el("rect", { x: bx, y: cy - rowH / 2, width: Math.max(w, 1), height: rowH, rx: 3, fill: item.color || (item.value >= 0 ? "#22c55e" : "#ef4444"), opacity: 0.85 }, svg);
    svgText(item.value >= 0 ? bx + w + 6 : bx - 6, cy + 4, (opts.vFmt || ((v) => fmtPct(v)))(item.value),
      { "text-anchor": item.value >= 0 ? "start" : "end", "font-size": 11.5, fill: "#e6eaf2", class: "num" }, svg);
  });
}

/* Vertical bar chart with a zero baseline. `items` = [{label, value, color}]. */
function barChartV(container, items, opts = {}) {
  const width = container.clientWidth || 800;
  const height = opts.height || 240;
  const ml = 48, mr = 12, mt = 14, mb = 40;
  const iw = width - ml - mr, ih = height - mt - mb;
  const maxAbs = Math.max(1, ...items.map((i) => Math.abs(i.value)));
  const pad = maxAbs * 0.1;
  const top = maxAbs + pad, bottom = -maxAbs - pad;

  container.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);

  const y = (v) => mt + ih - ((v - bottom) / (top - bottom)) * ih;
  const zeroY = y(0);
  el("line", { x1: ml, x2: ml + iw, y1: zeroY, y2: zeroY, stroke: "#2a3348", "stroke-width": 1 }, svg);

  const step = niceStep(top - bottom, 4);
  for (let g = -maxAbs; g <= maxAbs + 1e-9; g += step) {
    el("line", { x1: ml, x2: ml + iw, y1: y(g), y2: y(g), stroke: "#1c2333", "stroke-width": 1 }, svg);
    svgText(ml - 7, y(g) + 4, (opts.yFmt || ((v) => v.toFixed(1)))(g),
      { "text-anchor": "end", "font-size": 11, fill: "#5f6b82", class: "num" }, svg);
  }

  const slot = iw / items.length;
  const bw = Math.min(slot * 0.62, 46);
  items.forEach((item, i) => {
    const cx = ml + slot * i + slot / 2;
    const v = item.value;
    el("rect", {
      x: cx - bw / 2,
      y: v >= 0 ? y(v) : zeroY,
      width: bw,
      height: Math.max(Math.abs(y(v) - zeroY), 1),
      rx: 3,
      fill: item.color || (v >= 0 ? "#22c55e" : "#ef4444"),
      opacity: 0.85,
    }, svg);
    svgText(cx, height - mb + 18, item.label, { "text-anchor": "middle", "font-size": 10.5, fill: "#97a1b5" }, svg);
  });
}

/* ------------------------------------------------------------------ */
/* Interactive charts                                                   */
/* ------------------------------------------------------------------ */

/* Interactive multi-series line chart with a crosshair, hover tooltip,
   optional area fill and click-drag range zoom.

   opts: { height, yFmt, xFmt, area, onZoom(from,to), zoom:{from,to} } */
function interactiveLineChart(container, series, labels, opts = {}) {
  const width = container.clientWidth || 820;
  const height = opts.height || 300;
  const ml = opts.ml || 62, mr = 16, mt = 16, mb = 30;
  const iw = width - ml - mr, ih = height - mt - mb;

  const total = labels.length;
  const zf = opts.zoom ? Math.max(0, opts.zoom.from) : 0;
  const zt = opts.zoom ? Math.min(total - 1, opts.zoom.to) : total - 1;
  const view = series.map((s) => ({ ...s, values: s.values.slice(zf, zt + 1) }));
  const viewLabels = labels.slice(zf, zt + 1);
  const n = viewLabels.length;

  container.innerHTML = "";
  if (!n) { container.innerHTML = '<div class="empty">No data in range</div>'; return; }

  let all = [];
  view.forEach((s) => (all = all.concat(s.values.filter((v) => v != null))));
  if (!all.length) { container.innerHTML = '<div class="empty">No history yet</div>'; return; }
  let min = Math.min(...all), max = Math.max(...all);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.08;
  min -= pad; max += pad;

  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);
  const x = (i) => ml + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v) => mt + ih - ((v - min) / (max - min)) * ih;
  const yFmt = opts.yFmt || ((v) => v.toLocaleString("en-US", { maximumFractionDigits: 2 }));

  const step = niceStep(max - min, 5);
  for (let g = Math.ceil(min / step) * step; g <= max; g += step) {
    el("line", { x1: ml, x2: ml + iw, y1: y(g), y2: y(g), stroke: "#1c2333", "stroke-width": 1 }, svg);
    svgText(ml - 8, y(g) + 4, yFmt(g), { "text-anchor": "end", "font-size": 11, fill: "#5f6b82", class: "num" }, svg);
  }
  const every = Math.max(1, Math.ceil(n / (opts.ticks || 6)));
  for (let i = 0; i < n; i += every) {
    svgText(x(i), height - 8, viewLabels[i] || "", { "text-anchor": "middle", "font-size": 11, fill: "#5f6b82", class: "num" }, svg);
  }

  view.forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
    if (!pts.length) return;
    if (s.area) {
      el("path", {
        d: "M" + pts.map((p) => p.join(",")).join(" L") + ` L${pts[pts.length - 1][0]},${mt + ih} L${pts[0][0]},${mt + ih} Z`,
        fill: s.fill || "rgba(59,130,246,0.13)", stroke: "none",
      }, svg);
    }
    el("path", {
      d: "M" + pts.map((p) => p.join(",")).join(" L"),
      fill: "none", stroke: s.color || "#3b82f6", "stroke-width": s.width || 2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
      "stroke-dasharray": s.dashed ? "5 4" : null,
    }, svg);
  });

  /* crosshair + hover markers */
  const cross = el("line", { y1: mt, y2: mt + ih, stroke: "#3b82f6", "stroke-width": 1, "stroke-dasharray": "3 3", opacity: 0 }, svg);
  const dots = view.map((s) => el("circle", { r: 4, fill: s.color || "#3b82f6", stroke: "#0b0e14", "stroke-width": 2, opacity: 0 }, svg));
  const band = el("rect", { y: mt, height: ih, fill: "rgba(59,130,246,0.16)", opacity: 0 }, svg);

  const tip = document.createElement("div");
  tip.className = "tooltip";
  container.style.position = "relative";
  container.appendChild(tip);

  const hit = el("rect", { x: ml, y: mt, width: iw, height: ih, fill: "transparent", style: "cursor:crosshair" }, svg);

  const idxAt = (clientX) => {
    const r = container.getBoundingClientRect();
    const px = ((clientX - r.left) / r.width) * width;
    return Math.max(0, Math.min(n - 1, Math.round(((px - ml) / iw) * (n - 1))));
  };

  let dragStart = null;

  function showAt(i) {
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", 1);
    view.forEach((s, k) => {
      const v = s.values[i];
      if (v == null) { dots[k].setAttribute("opacity", 0); return; }
      dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); dots[k].setAttribute("opacity", 1);
    });
    tip.innerHTML =
      `<div class="t-head">${esc(viewLabels[i])}</div>` +
      view.map((s) => s.values[i] == null ? "" :
        `<div class="t-row"><span class="sw" style="background:${s.color}"></span>${esc(s.name)}<b class="num">${yFmt(s.values[i])}</b></div>`
      ).join("");
    tip.style.opacity = 1;
    const relX = (x(i) / width) * container.clientWidth;
    tip.style.left = Math.min(Math.max(relX + 14, 4), container.clientWidth - tip.offsetWidth - 4) + "px";
    tip.style.top = "10px";
  }
  function hide() {
    cross.setAttribute("opacity", 0);
    dots.forEach((d) => d.setAttribute("opacity", 0));
    tip.style.opacity = 0;
  }

  hit.addEventListener("mousemove", (e) => {
    const i = idxAt(e.clientX);
    showAt(i);
    if (dragStart != null) {
      const a = Math.min(dragStart, i), b = Math.max(dragStart, i);
      band.setAttribute("x", x(a)); band.setAttribute("width", Math.max(1, x(b) - x(a))); band.setAttribute("opacity", 1);
    }
  });
  hit.addEventListener("mouseleave", () => { hide(); dragStart = null; band.setAttribute("opacity", 0); });
  hit.addEventListener("mousedown", (e) => { dragStart = idxAt(e.clientX); });
  hit.addEventListener("mouseup", (e) => {
    if (dragStart == null) return;
    const i = idxAt(e.clientX);
    const a = Math.min(dragStart, i), b = Math.max(dragStart, i);
    dragStart = null; band.setAttribute("opacity", 0);
    if (b - a >= 2 && opts.onZoom) opts.onZoom(zf + a, zf + b);
  });
  hit.addEventListener("dblclick", () => { if (opts.onZoom) opts.onZoom(0, total - 1); });

  return { from: zf, to: zt };
}

/* Clickable legend. `series` entries get a `visible` flag toggled in place. */
function legend(container, series, onChange) {
  const host = typeof container === "string" ? document.querySelector(container) : container;
  if (!host) return;
  host.innerHTML = "";
  series.forEach((s) => {
    const item = document.createElement("div");
    item.className = "item" + (s.visible === false ? " off" : "");
    item.innerHTML = `<span class="swatch" style="background:${s.color}"></span>${esc(s.name)}`;
    item.onclick = () => {
      s.visible = s.visible === false;
      item.classList.toggle("off", s.visible === false);
      onChange && onChange();
    };
    host.appendChild(item);
  });
}

/* Candlestick-style OHLC chart driven by history rows (uses price only when
   OHLC is unavailable, drawing a stepped price line instead). */
function priceChart(container, rows, opts = {}) {
  const series = [{ name: "Price", color: "#f59e0b", area: true, fill: "rgba(245,158,11,0.10)", values: rows.map((r) => r.price) }];
  return interactiveLineChart(container, series, rows.map((r) => fmtTsShort(r.ts)), {
    ...opts, yFmt: (v) => "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 }),
  });
}

/* Simple histogram of values into `bins` buckets. */
function histogram(container, values, opts = {}) {
  const width = container.clientWidth || 800;
  const height = opts.height || 240;
  const ml = 44, mr = 12, mt = 14, mb = 34;
  const iw = width - ml - mr, ih = height - mt - mb;
  container.innerHTML = "";
  if (!values.length) { container.innerHTML = '<div class="empty">No data</div>'; return; }

  const bins = opts.bins || 12;
  const lo = Math.min(...values), hi = Math.max(...values);
  const span = hi - lo || 1;
  const counts = new Array(bins).fill(0);
  values.forEach((v) => {
    const k = Math.min(bins - 1, Math.floor(((v - lo) / span) * bins));
    counts[k]++;
  });
  const maxC = Math.max(...counts);
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);
  const slot = iw / bins;
  counts.forEach((c, i) => {
    const h = (c / maxC) * ih;
    const binLo = lo + (span * i) / bins;
    const r = el("rect", {
      x: ml + slot * i + 2, y: mt + ih - h, width: Math.max(1, slot - 4), height: Math.max(c ? 2 : 0, h),
      rx: 3, fill: binLo >= 0 ? "#22c55e" : "#ef4444", opacity: 0.85,
    }, svg);
    const t = el("title", {}, r);
    t.textContent = `${(opts.fmt || fmtPct)(binLo)} → ${(opts.fmt || fmtPct)(binLo + span / bins)}: ${c}`;
    if (i % Math.ceil(bins / 6) === 0) {
      svgText(ml + slot * i + slot / 2, height - 10, (opts.fmt || fmtPct)(binLo),
        { "text-anchor": "middle", "font-size": 10.5, fill: "#5f6b82", class: "num" }, svg);
    }
    if (c) svgText(ml + slot * i + slot / 2, mt + ih - h - 5, String(c),
      { "text-anchor": "middle", "font-size": 10.5, fill: "#97a1b5", class: "num" }, svg);
  });
  el("line", { x1: ml, x2: ml + iw, y1: mt + ih, y2: mt + ih, stroke: "#2a3348" }, svg);
}

/* Scatter plot. `points` = [{x, y, label, color}] */
function scatterChart(container, points, opts = {}) {
  const width = container.clientWidth || 800;
  const height = opts.height || 280;
  const ml = 56, mr = 16, mt = 16, mb = 38;
  const iw = width - ml - mr, ih = height - mt - mb;
  container.innerHTML = "";
  if (!points.length) { container.innerHTML = '<div class="empty">No data</div>'; return; }

  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  let x0 = Math.min(0, ...xs), x1 = Math.max(1, ...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const padY = (y1 - y0) * 0.1; y0 -= padY; y1 += padY;

  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart" }, container);
  const X = (v) => ml + ((v - x0) / (x1 - x0)) * iw;
  const Y = (v) => mt + ih - ((v - y0) / (y1 - y0)) * ih;

  const stepY = niceStep(y1 - y0, 4);
  for (let g = Math.ceil(y0 / stepY) * stepY; g <= y1; g += stepY) {
    el("line", { x1: ml, x2: ml + iw, y1: Y(g), y2: Y(g), stroke: "#1c2333" }, svg);
    svgText(ml - 8, Y(g) + 4, (opts.yFmt || ((v) => v.toFixed(1)))(g),
      { "text-anchor": "end", "font-size": 11, fill: "#5f6b82", class: "num" }, svg);
  }
  const stepX = niceStep(x1 - x0, 5);
  for (let g = Math.ceil(x0 / stepX) * stepX; g <= x1; g += stepX) {
    svgText(X(g), height - 12, (opts.xFmt || ((v) => v.toFixed(0)))(g),
      { "text-anchor": "middle", "font-size": 11, fill: "#5f6b82", class: "num" }, svg);
  }
  if (y0 < 0 && y1 > 0) el("line", { x1: ml, x2: ml + iw, y1: Y(0), y2: Y(0), stroke: "#2a3348" }, svg);

  points.forEach((p) => {
    const c = el("circle", {
      cx: X(p.x), cy: Y(p.y), r: p.r || 5,
      fill: p.color || (p.y >= 0 ? "#22c55e" : "#ef4444"), opacity: 0.8,
      style: p.href ? "cursor:pointer" : "",
    }, svg);
    const t = el("title", {}, c);
    t.textContent = `${p.label}: ${(opts.xFmt || ((v) => v))(p.x)} / ${(opts.yFmt || ((v) => v))(p.y)}`;
    c.addEventListener("mouseenter", () => c.setAttribute("r", (p.r || 5) + 3));
    c.addEventListener("mouseleave", () => c.setAttribute("r", p.r || 5));
    if (p.href) c.addEventListener("click", () => (location.href = p.href));
  });
  svgText(ml + iw / 2, height - 1, opts.xLabel || "", { "text-anchor": "middle", "font-size": 11, fill: "#5f6b82" }, svg);
}

/* Donut chart. `items` = [{label, value, color}] */
function donutChart(container, items, opts = {}) {
  const size = opts.size || 220;
  const width = container.clientWidth || size;
  const r = size / 2 - 8, cx = size / 2, cy = size / 2, inner = r * 0.62;
  container.innerHTML = "";
  const total = items.reduce((s, i) => s + Math.max(0, i.value), 0);
  if (!total) { container.innerHTML = '<div class="empty">No data</div>'; return; }
  const svg = el("svg", { viewBox: `0 0 ${size} ${size}`, class: "chart", style: `max-width:${size}px;margin:0 auto;display:block` }, container);
  let a0 = -Math.PI / 2;
  items.forEach((it) => {
    const v = Math.max(0, it.value);
    if (!v) return;
    const a1 = a0 + (v / total) * Math.PI * 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (ang, rad) => [cx + Math.cos(ang) * rad, cy + Math.sin(ang) * rad];
    const [x0, y0] = p(a0, r), [x1, y1] = p(a1, r), [x2, y2] = p(a1, inner), [x3, y3] = p(a0, inner);
    const path = el("path", {
      d: `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${inner},${inner} 0 ${large} 0 ${x3},${y3} Z`,
      fill: it.color, opacity: 0.9,
    }, svg);
    const t = el("title", {}, path);
    t.textContent = `${it.label}: ${((v / total) * 100).toFixed(1)}%`;
    path.addEventListener("mouseenter", () => path.setAttribute("opacity", 1));
    path.addEventListener("mouseleave", () => path.setAttribute("opacity", 0.9));
    a0 = a1;
  });
  svgText(cx, cy + 5, opts.center || "", { "text-anchor": "middle", "font-size": 15, fill: "#e6eaf2", class: "num" }, svg);
}

/* Heatmap grid. `rows` = [{label, cells:[{label,value}]}] */
function heatmap(container, rows, opts = {}) {
  container.innerHTML = "";
  if (!rows.length) { container.innerHTML = '<div class="empty">No data</div>'; return; }
  const maxAbs = Math.max(1e-9, ...rows.flatMap((r) => r.cells.map((c) => Math.abs(c.value || 0))));
  const html = rows.map((r) => `
    <div class="hm-row">
      <div class="hm-label">${esc(r.label)}</div>
      <div class="hm-cells">${r.cells.map((c) => {
        const v = c.value || 0;
        const alpha = Math.min(0.85, Math.abs(v) / maxAbs * 0.85 + 0.05);
        const col = v >= 0 ? `rgba(34,197,94,${alpha})` : `rgba(239,68,68,${alpha})`;
        return `<div class="hm-cell" style="background:${col}" title="${esc(c.label)}: ${(opts.fmt || fmtPct)(v)}">${opts.showValues ? (opts.fmt || fmtPct)(v) : ""}</div>`;
      }).join("")}</div>
    </div>`).join("");
  container.innerHTML = `<div class="hm">${html}</div>`;
}
