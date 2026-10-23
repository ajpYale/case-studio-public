// Minimal SVG charts for case exhibits — no libraries, so the app works offline.
// An exhibit's first column holds category labels; each further column is a series.
"use strict";

const CHART_COLORS = ["#00356b", "#63aaff", "#978d85", "#286dc0", "#5f712d", "#bd5319", "#4a4a4a", "#aac7ec"];
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}, text) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text !== undefined) el.textContent = text;
  return el;
}

function niceMax(v) {
  if (v <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * exp >= v) return m * exp;
  return 10 * exp;
}

function shortNum(v, unit) {
  const a = Math.abs(v);
  if (a < 1e-12 && unit !== "pct") return ["usd", "usd_k", "usd_m", "usd_b", "per_unit_usd"].includes(unit) ? "$0" : "0";
  let s;
  if (unit === "pct") s = `${+(v * 100).toFixed(a * 100 >= 10 ? 0 : 1)}%`;
  else if (a >= 1e9) s = `${+(v / 1e9).toFixed(1)}B`;
  else if (a >= 1e6) s = `${+(v / 1e6).toFixed(1)}M`;
  else if (a >= 1e4) s = `${+(v / 1e3).toFixed(0)}K`;
  else s = `${+v.toFixed(a >= 100 ? 0 : a >= 10 ? 1 : 2)}`;
  const pre = ["usd", "usd_k", "usd_m", "usd_b", "per_unit_usd"].includes(unit) ? "$" : "";
  const post = { usd_k: "K", usd_m: "M", usd_b: "B", count_k: "K", count_m: "M", multiple: "x" }[unit] || "";
  return pre + s + (unit === "pct" ? "" : post);
}

function seriesOf(ex) {
  const names = ex.columns.slice(1);
  const series = names.map((name, j) => ({
    name,
    unit: (ex.units && ex.units[j]) || ex.value_unit,
    values: ex.grid.map(row => (typeof row[j] === "number" ? row[j] : null)),
  })).filter(s => s.values.some(v => v !== null));
  const cats = ex.rows.map(r => r.label);
  // Drop "Total" rows from charts — they distort the scale.
  const keep = cats.map(c => !/^(total|sum)\b/i.test(c.trim()));
  return {
    cats: cats.filter((_, i) => keep[i]),
    series: series.map(s => ({ ...s, values: s.values.filter((_, i) => keep[i]) })),
  };
}

function legend(series) {
  const div = document.createElement("div");
  div.className = "legend";
  series.forEach((s, i) => {
    const span = document.createElement("span");
    const sw = document.createElement("i");
    sw.style.background = CHART_COLORS[i % CHART_COLORS.length];
    span.append(sw, document.createTextNode(s.name));
    div.append(span);
  });
  return div;
}

function axisFrame(svg, W, H, pad, lo, hi, unit) {
  const ticks = 4;
  for (let t = 0; t <= ticks; t++) {
    const v = lo + ((hi - lo) * t) / ticks;
    const y = pad.t + (H - pad.t - pad.b) * (1 - (v - lo) / (hi - lo));
    svg.append(svgEl("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, stroke: "#e4e4e4", "stroke-width": 1 }));
    svg.append(svgEl("text", { x: pad.l - 8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "#6b6b6b" }, shortNum(v, unit)));
  }
}

function yScale(H, pad, lo, hi) {
  return v => pad.t + (H - pad.t - pad.b) * (1 - (v - lo) / (hi - lo));
}

// Category labels wrap onto up to two lines sized to the column width; only a third line's worth is cut.
function wrapLabel(text, maxChars) {
  const lines = [];
  for (const w of text.split(/\s+/)) {
    const cur = lines.length ? lines[lines.length - 1] : null;
    if (cur !== null && (cur + " " + w).length <= maxChars) lines[lines.length - 1] = cur + " " + w;
    else lines.push(w);
  }
  if (lines.length <= 2) return lines.map((l) => (l.length > maxChars ? l.slice(0, maxChars - 1) + "…" : l));
  const second = lines.slice(1).join(" ");
  return [lines[0].slice(0, maxChars), second.slice(0, maxChars - 1).trimEnd() + "…"];
}

function catLabels(svg, cats, x0, step, y) {
  const maxChars = Math.max(8, Math.floor(step / 6.6));
  cats.forEach((c, i) => {
    const lines = wrapLabel(c, maxChars);
    const t = svgEl("text", { x: x0 + step * i + step / 2, y, "text-anchor": "middle", "font-size": 11.5, fill: "#4a4a4a" });
    lines.forEach((line, k) => t.append(svgEl("tspan", { x: x0 + step * i + step / 2, dy: k === 0 ? 0 : 14 }, line)));
    t.append(svgEl("title", {}, c));
    svg.append(t);
  });
}

function barChart(ex, stacked) {
  const { cats, series } = seriesOf(ex);
  const W = 720, H = 320, pad = { t: 20, r: 16, b: 40, l: 64 };
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": ex.title });
  const totals = cats.map((_, i) => series.reduce((a, s) => a + Math.max(0, s.values[i] || 0), 0));
  const all = series.flatMap(s => s.values.filter(v => v !== null));
  const hi = niceMax(stacked ? Math.max(...totals, 0) : Math.max(...all, 0));
  const lo = Math.min(0, ...all) < 0 ? -niceMax(-Math.min(...all)) : 0;
  axisFrame(svg, W, H, pad, lo, hi, (series[0] || {}).unit || ex.value_unit);
  const y = yScale(H, pad, lo, hi);
  const step = (W - pad.l - pad.r) / Math.max(cats.length, 1);
  const groupW = step * 0.68;
  cats.forEach((_, i) => {
    const gx = pad.l + step * i + (step - groupW) / 2;
    let base = 0;
    series.forEach((s, j) => {
      const v = s.values[i];
      if (v === null) return;
      const color = CHART_COLORS[j % CHART_COLORS.length];
      if (stacked) {
        const y1 = y(base + v), y0 = y(base);
        svg.append(svgEl("rect", { x: gx, y: Math.min(y0, y1), width: groupW, height: Math.abs(y0 - y1), fill: color }));
        if (Math.abs(y0 - y1) > 16) svg.append(svgEl("text", { x: gx + groupW / 2, y: (y0 + y1) / 2 + 4, "text-anchor": "middle", "font-size": 10.5, fill: j === 1 || j === 7 ? "#00254c" : "#fff" }, shortNum(v, s.unit)));
        base += v;
      } else {
        const bw = groupW / series.length;
        const x = gx + bw * j;
        const y1 = y(v), y0 = y(0);
        svg.append(svgEl("rect", { x: x + 1, y: Math.min(y0, y1), width: Math.max(bw - 2, 2), height: Math.abs(y0 - y1), fill: color }));
        if (series.length <= 3 && cats.length <= 10) {
          svg.append(svgEl("text", { x: x + bw / 2, y: v >= 0 ? y1 - 5 : y1 + 13, "text-anchor": "middle", "font-size": 10.5, fill: "#222" }, shortNum(v, s.unit)));
        }
      }
    });
  });
  svg.append(svgEl("line", { x1: pad.l, x2: W - pad.r, y1: y(0), y2: y(0), stroke: "#222", "stroke-width": 1 }));
  catLabels(svg, cats, pad.l, step, H - pad.b + 18);
  return wrapChart(svg, series);
}

function lineChart(ex) {
  const { cats, series } = seriesOf(ex);
  const W = 720, H = 320, pad = { t: 20, r: 20, b: 40, l: 64 };
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": ex.title });
  const all = series.flatMap(s => s.values.filter(v => v !== null));
  const hi = niceMax(Math.max(...all, 0));
  const lo = Math.min(0, ...all) < 0 ? -niceMax(-Math.min(...all)) : 0;
  axisFrame(svg, W, H, pad, lo, hi, (series[0] || {}).unit || ex.value_unit);
  const y = yScale(H, pad, lo, hi);
  const step = (W - pad.l - pad.r) / Math.max(cats.length, 1);
  series.forEach((s, j) => {
    const color = CHART_COLORS[j % CHART_COLORS.length];
    const pts = s.values.map((v, i) => (v === null ? null : [pad.l + step * i + step / 2, y(v)])).filter(Boolean);
    svg.append(svgEl("polyline", { points: pts.map(p => p.join(",")).join(" "), fill: "none", stroke: color, "stroke-width": 2.5 }));
    pts.forEach(([px, py], k) => {
      svg.append(svgEl("circle", { cx: px, cy: py, r: 3.5, fill: color }));
      if (series.length <= 2) svg.append(svgEl("text", { x: px, y: py - 9, "text-anchor": "middle", "font-size": 10.5, fill: "#222" }, shortNum(s.values.filter(v => v !== null)[k], s.unit)));
    });
  });
  catLabels(svg, cats, pad.l, step, H - pad.b + 18);
  return wrapChart(svg, series);
}

function pieChart(ex) {
  const { cats, series } = seriesOf(ex);
  const s = series[0];
  const W = 720, H = 300, cx = 170, cy = 150, r = 120;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": ex.title });
  const vals = s ? s.values.map(v => Math.max(0, v || 0)) : [];
  const total = vals.reduce((a, b) => a + b, 0) || 1;
  let a0 = -Math.PI / 2;
  vals.forEach((v, i) => {
    const a1 = a0 + (v / total) * Math.PI * 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    const color = CHART_COLORS[i % CHART_COLORS.length];
    const d = vals.length === 1 ? `M ${cx - r} ${cy} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0`
      : `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;
    svg.append(svgEl("path", { d, fill: color, stroke: "#fff", "stroke-width": 1.5 }));
    const ly = 40 + i * 26;
    svg.append(svgEl("rect", { x: 340, y: ly - 11, width: 12, height: 12, fill: color }));
    const share = s.unit === "pct" ? "" : ` (${Math.round((v / total) * 100)}%)`;
    svg.append(svgEl("text", { x: 360, y: ly, "font-size": 14, fill: "#222" }, `${cats[i]} — ${shortNum(v, s.unit)}${share}`));
    a0 = a1;
  });
  const div = document.createElement("div");
  div.className = "chart";
  div.append(svg);
  return div;
}

function wrapChart(svg, series) {
  const div = document.createElement("div");
  div.className = "chart";
  div.append(svg);
  if (series.length > 1) div.append(legend(series));
  return div;
}

function renderChart(ex) {
  if (ex.kind === "bar") return barChart(ex, false);
  if (ex.kind === "stacked_bar") return barChart(ex, true);
  if (ex.kind === "line") return lineChart(ex);
  if (ex.kind === "pie") return pieChart(ex);
  return null;
}
