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
