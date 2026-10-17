// Interactive charts: the zoomable rating line, the eval graph, the
// average-eval curves. Plain SVG, no library.

import { esc, resultCls, resultMark } from "./api.js";

const NS = "http://www.w3.org/2000/svg";

// ---------------------------------------------------------------- rating line

export function buildRatingChart(host, series, ma = false, yMax = null, onPick = null) {
  const pts = (series[0] && series[0].points) || [];
  const data = pts.map((p, i) => ({ i, date: p.x, y: p.y, src: p }));
  if (data.length < 2) return;
  const W = host.clientWidth || 880, H = 280;
  const M = { l: 46, r: 14, t: 12, b: 26 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;
  const n = data.length;
  let dom = [0, n - 1], curYd = [0, 1], brushing = false, startX = 0;

  const maWin = ma ? Math.min(30, Math.max(3, Math.round(n / 8))) : 0;
  const maY = ma ? data.map((_, i) => {
    const lo = Math.max(0, i - maWin + 1);
    let s = 0;
    for (let j = lo; j <= i; j++) s += data[j].y;
    return s / (i - lo + 1);
  }) : null;

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const tip = document.createElement("div"); tip.className = "chart-tip";
  const show = { raw: true, ma: true };
  if (ma) {
    const leg = document.createElement("div"); leg.className = "evc-legend";
    const renderLeg = () => {
      leg.innerHTML =
        `<button class="evc-key${show.raw ? "" : " off"}" data-k="raw">` +
        `<span class="evc-sw" style="background:var(--mut)"></span>Rating</button>` +
        `<button class="evc-key${show.ma ? "" : " off"}" data-k="ma">` +
        `<span class="evc-sw" style="background:var(--accent)"></span>${maWin}-game average</button>`;
    };
    renderLeg();
    leg.onclick = (e) => {
      const b = e.target.closest(".evc-key"); if (!b) return;
      const k = b.dataset.k;
      if (show[k] && (show.raw ? 1 : 0) + (show.ma ? 1 : 0) <= 1) return;
      show[k] = !show[k];
      renderLeg(); draw();
    };
    host.appendChild(leg);
  }
  host.appendChild(svg); host.appendChild(tip);

  const visible = () => data.filter((d) => d.i >= Math.ceil(dom[0]) && d.i <= Math.floor(dom[1]));
  const xPix = (i) => M.l + ((i - dom[0]) / (dom[1] - dom[0])) * pw;
  const yPix = (v) => M.t + (1 - (v - curYd[0]) / (curYd[1] - curYd[0])) * ph;
  const toVbX = (e) => { const r = svg.getBoundingClientRect(); return (e.clientX - r.left) * (W / r.width); };

  function draw() {
    const vs = visible();
    const vals = [];
    if (show.raw) vs.forEach((d) => vals.push(d.y));
    if (maY && show.ma) vs.forEach((d) => vals.push(maY[d.i]));
    if (!vals.length) vs.forEach((d) => vals.push(d.y));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (lo === hi) { lo -= 10; hi += 10; }
    const pad = (hi - lo) * 0.12 || 8; curYd = [lo - pad, hi + pad];
    if (yMax !== null && curYd[1] > yMax) curYd[1] = yMax;
    let s = "";
    for (let t = 0; t <= 4; t++) {
      const val = curYd[0] + ((curYd[1] - curYd[0]) * t) / 4, y = yPix(val);
      s += `<line class="chart-grid" x1="${M.l}" y1="${y.toFixed(1)}" x2="${W - M.r}" y2="${y.toFixed(1)}"/>`;
      s += `<text x="${M.l - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end">${Math.round(val)}</text>`;
    }
    for (let t = 0; t <= 5; t++) {
      const idx = Math.round(dom[0] + ((dom[1] - dom[0]) * t) / 5), d = data[idx];
      if (d) s += `<text x="${xPix(idx).toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(String(d.date).slice(5))}</text>`;
    }
    if (vs.length) {
      const base = (M.t + ph).toFixed(1);
      if (show.raw) {
        const pp = vs.map((d) => `${xPix(d.i).toFixed(1)},${yPix(d.y).toFixed(1)}`);
        const dim = ma ? " muted" : "";
        s += `<polygon class="chart-area${dim}" points="${xPix(vs[0].i).toFixed(1)},${base} ${pp.join(" ")} ${xPix(vs[vs.length - 1].i).toFixed(1)},${base}"/>`;
        s += `<polyline class="chart-line${dim}" points="${pp.join(" ")}"/>`;
      }
      if (maY && show.ma) {
        const mp = vs.map((d) => `${xPix(d.i).toFixed(1)},${yPix(maY[d.i]).toFixed(1)}`);
        s += `<polyline class="chart-line-ma" points="${mp.join(" ")}"/>`;
      }
    }
    s += `<g class="guide" style="display:none"><line class="chart-guide" y1="${M.t}" y2="${M.t + ph}"/>` +
      `<circle class="chart-dot" r="4"/></g>`;
    s += `<rect class="brush chart-brush" y="${M.t}" height="${ph}" width="0" style="display:none"/>`;
    s += `<rect class="ov" x="${M.l}" y="${M.t}" width="${pw}" height="${ph}" fill="transparent"/>`;
    svg.innerHTML = s;
    bindOverlay();
  }

  function bindOverlay() {
    const ov = svg.querySelector(".ov"), guide = svg.querySelector(".guide");
    const gl = guide.querySelector("line"), dot = guide.querySelector("circle");
    const brush = svg.querySelector(".brush");
    ov.onmousemove = (e) => {
      const px = toVbX(e);
      if (brushing) {
        const x0 = Math.min(startX, px), x1 = Math.max(startX, px);
        brush.style.display = ""; brush.setAttribute("x", x0); brush.setAttribute("width", x1 - x0);
        tip.style.opacity = 0; guide.style.display = "none"; return;
      }
      let idx = Math.round(dom[0] + ((px - M.l) / pw) * (dom[1] - dom[0]));
      idx = Math.max(Math.ceil(dom[0]), Math.min(Math.floor(dom[1]), idx));
      const d = data[idx]; if (!d) return;
      const yVal = show.raw ? d.y : maY[idx];
      const x = xPix(idx), y = yPix(yVal);
      guide.style.display = ""; gl.setAttribute("x1", x); gl.setAttribute("x2", x);
      dot.setAttribute("cx", x); dot.setAttribute("cy", y);
      let info = "";
      if (show.raw) {
        const prev = data[idx - 1];
        const ch = prev ? Math.round((d.y - prev.y) * 10) / 10 : null;
        const chTxt = ch === null ? "" : ch >= 0 ? `<span class="up">▲ +${ch}</span>` : `<span class="dn">▼ ${ch}</span>`;
        info += `<b>${d.y}</b> ${chTxt}`;
      }
      if (maY && show.ma) info += `${show.raw ? " · " : ""}avg <b>${Math.round(maY[idx])}</b>`;
      tip.innerHTML = `${esc(d.date)} · ${info}`;
      const r = svg.getBoundingClientRect();
      tip.style.left = (x * (r.width / W)) + "px";
      tip.style.top = (y * (r.height / H)) + "px"; tip.style.opacity = 1;
    };
    ov.onmouseleave = () => { if (!brushing) { tip.style.opacity = 0; guide.style.display = "none"; } };
    ov.onmousedown = (e) => { startX = toVbX(e); brushing = true; };
    ov.onwheel = (e) => {
      e.preventDefault();
      const px = toVbX(e), frac = (px - M.l) / pw;
      const center = dom[0] + frac * (dom[1] - dom[0]), span = dom[1] - dom[0];
      const ns = Math.max(4, Math.min(n - 1, span * (e.deltaY < 0 ? 0.8 : 1.25)));
      let a = center - (center - dom[0]) * (ns / span), b = a + ns;
      a = Math.max(0, a); b = Math.min(n - 1, b);
      if (b - a >= 3) { dom = [a, b]; draw(); }
    };
  }

  const onUp = (e) => {
    if (!document.body.contains(host)) { window.removeEventListener("mouseup", onUp); return; }
    if (!brushing) return; brushing = false;
    const brush = svg.querySelector(".brush"); if (brush) brush.style.display = "none";
    const x0 = Math.min(startX, toVbX(e)), x1 = Math.max(startX, toVbX(e));
    if (x1 - x0 > 6) {
      let a = Math.floor(dom[0] + ((x0 - M.l) / pw) * (dom[1] - dom[0]));
      let b = Math.ceil(dom[0] + ((x1 - M.l) / pw) * (dom[1] - dom[0]));
      a = Math.max(0, a); b = Math.min(n - 1, b);
      if (b - a >= 1) { dom = [a, b]; draw(); }
    } else if (onPick) {
      let idx = Math.round(dom[0] + ((x0 - M.l) / pw) * (dom[1] - dom[0]));
      idx = Math.max(Math.ceil(dom[0]), Math.min(Math.floor(dom[1]), idx));
      if (data[idx]) onPick(data[idx]);
    }
  };
  window.addEventListener("mouseup", onUp);
  svg.addEventListener("dblclick", () => { dom = [0, n - 1]; draw(); });
  draw();
}

// Bucket chronological points by period. agg="mean" averages each period
// (accuracy); default keeps the last value (closing rating).
export function aggregate(points, gran, agg = "last") {
  if (gran === "game") return points;
  const key = gran === "month" ? (x) => String(x).slice(0, 7) : (x) => x;
  const m = new Map();
  if (agg === "mean") {
    for (const p of points) {
      const k = key(p.x), e = m.get(k) || { x: k, sum: 0, n: 0 };
      e.sum += p.y; e.n += 1; m.set(k, e);
    }
    return [...m.values()].map((e) => ({ x: e.x, y: Math.round((e.sum / e.n) * 10) / 10 }));
  }
  for (const p of points) m.set(key(p.x), { x: key(p.x), y: p.y });
  return [...m.values()];
}

export function initChart(host, series, agg = "last", ma = false, yMax = null) {
  let gran = "game";
  const bar = document.createElement("div"); bar.className = "chart-toolbar";
  const wrap = document.createElement("div"); wrap.className = "chart-wrap";
  const hint = document.createElement("div"); hint.className = "chart-hint";
  hint.textContent = "drag / scroll to zoom · double-click to reset";
  ["game", "day", "month"].forEach((g) => {
    const b = document.createElement("button");
    b.className = "gbtn" + (g === gran ? " on" : "");
    b.textContent = g[0].toUpperCase() + g.slice(1);
    b.onclick = () => {
      gran = g;
      [...bar.children].forEach((c) => c.classList.toggle("on", c === b));
      render();
    };
    bar.appendChild(b);
  });
  host.appendChild(bar); host.appendChild(wrap); host.appendChild(hint);
  function render() {
    wrap.innerHTML = "";
    buildRatingChart(wrap, [{ name: series[0].name, points: aggregate(series[0].points, gran, agg) }], ma, yMax);
  }
  render();
}

// A line chart whose series is swapped by a toolbar (the form chart's 10/20/30
// game windows). With a games roster, clicking a point lists its window.
export function initVariantChart(host, variants, yMax = null, games = null) {
  let cur = variants.find((v) => v.default) || variants[0];
  const bar = document.createElement("div"); bar.className = "chart-toolbar";
  const wrap = document.createElement("div"); wrap.className = "chart-wrap";
  const hint = document.createElement("div"); hint.className = "chart-hint";
  const detail = document.createElement("div");
  hint.textContent = "drag / scroll to zoom · double-click to reset" + (games ? " · click a point to see its games" : "");
  variants.forEach((v) => {
    const b = document.createElement("button");
    b.className = "gbtn" + (v === cur ? " on" : "");
    b.textContent = v.label;
    b.onclick = () => { cur = v; [...bar.children].forEach((c) => c.classList.toggle("on", c === b)); render(); };
    bar.appendChild(b);
  });
  host.append(bar, wrap, hint, detail);

  function showWindow(d) {
    const p = d.src || {};
    if (p.i0 == null || p.i1 == null) return;
    const win = games.slice(p.i0, p.i1);
    const rows = win.slice().reverse().map((g) =>
      `<tr class="rrow" data-game-id="${esc(g.id)}"><td class="${resultCls(g.outcome)}">${resultMark(g.outcome)}</td>` +
      `<td>${esc(g.date)}</td><td>${esc(g.opponent)} (${g.opp_elo || "?"})</td></tr>`).join("");
    const count = (o) => win.filter((g) => g.outcome === o).length;
    detail.innerHTML = `<div class="reasons-head">Performance ${d.y} — the ${win.length} games ending ` +
      `${esc(d.date)} (${count("win")}-${count("draw")}-${count("loss")}, newest first) ` +
      `<a href="#" class="vc-close">✕ close</a></div>` +
      `<table class="recent-tbl reason-games"><tbody>${rows}</tbody></table>`;
    detail.querySelector(".vc-close").onclick = (e) => { e.preventDefault(); detail.innerHTML = ""; };
  }
  function render() {
    wrap.innerHTML = ""; detail.innerHTML = "";
    buildRatingChart(wrap, [{ name: cur.label, points: cur.points }], false, yMax, games ? showWindow : null);
  }
  render();
}

// ---------------------------------------------------------------- eval graph

const DOT = { inaccuracy: "var(--inacc)", mistake: "var(--mist)", blunder: "var(--blun)" };

export function buildEvalChart(host, plies, moves, me, division = null) {
  if (!plies || plies.length < 2) return;
  let filter = "both";
  const colorAt = (i) => (i % 2 === 1 ? "white" : "black");
  const showDot = (p, i) => DOT[p.label] && i > 0 &&
    (filter === "both" || (colorAt(i) === me) === (filter === "mine"));
  // a flagged move's dot sits on the position it was played from
  const flagAt = (i) => (plies[i + 1] && showDot(plies[i + 1], i + 1) ? plies[i + 1].label : null);

  const bar = document.createElement("div"); bar.className = "chart-toolbar";
  [["Both", "both"], ["Mine", "mine"], ["Opponent", "theirs"]].forEach(([lbl, val]) => {
    const b = document.createElement("button");
    b.className = "gbtn" + (val === filter ? " on" : "");
    b.textContent = lbl;
    b.onclick = () => {
      filter = val;
      [...bar.children].forEach((c) => c.classList.toggle("on", c === b));
      svg.querySelector(".ev-dots").innerHTML = dotStr();
    };
    bar.appendChild(b);
  });
  host.appendChild(bar);

  const W = host.clientWidth || 880, H = 210;
  const M = { l: 34, r: 10, t: 14, b: 22 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;
  const n = plies.length, CLAMP = 1000;
  const clamp = (c) => Math.max(-CLAMP, Math.min(CLAMP, c));
  const xPix = (i) => M.l + (i / (n - 1)) * pw;
  const yPix = (c) => M.t + ph * (0.5 - clamp(c) / (2 * CLAMP));

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.classList.add("evalc");
  const tip = document.createElement("div"); tip.className = "chart-tip";
  host.appendChild(svg); host.appendChild(tip);

  const curve = plies.map((p, i) => `${xPix(i).toFixed(1)},${yPix(p.cp).toFixed(1)}`);
  const base = (M.t + ph).toFixed(1);
  const dotStr = () => plies.map((p, i) => {
    const lab = flagAt(i);
    return lab ? `<circle class="ev-dot" cx="${xPix(i).toFixed(1)}" cy="${yPix(p.cp).toFixed(1)}" r="5" fill="${DOT[lab]}"/>` : "";
  }).join("");

  let axes = "";
  for (const cpv of [800, 500, 200, 0, -200, -500, -800]) {
    const y = yPix(cpv).toFixed(1);
    axes += `<line class="${cpv === 0 ? "ev-zero" : "ev-grid"}" x1="${M.l}" y1="${y}" x2="${M.l + pw}" y2="${y}"/>`;
    axes += `<text class="ev-ax" x="${M.l - 5}" y="${(+y + 3).toFixed(1)}" text-anchor="end">${cpv > 0 ? "+" + cpv / 100 : cpv / 100}</text>`;
  }
  for (let t = 0; t <= 5; t++) {
    const i = Math.round((t / 5) * (n - 1));
    axes += `<text class="ev-ax" x="${xPix(i).toFixed(1)}" y="${H - 6}" text-anchor="middle">${Math.max(1, Math.ceil(i / 2))}</text>`;
  }
  // where the middlegame and endgame begin (phases.py, by position)
  let phases = "";
  if (division) {
    for (const [pos, label] of [[division.mid, "middlegame"], [division.end, "endgame"]]) {
      if (pos == null || pos <= 0 || pos >= n) continue;
      const x = xPix(pos).toFixed(1);
      phases += `<line class="ev-phase" x1="${x}" x2="${x}" y1="${M.t}" y2="${M.t + ph}"/>` +
        `<text class="ev-phase-l" x="${(+x + 3).toFixed(1)}" y="${M.t - 3}">${label}</text>`;
    }
  }

  svg.innerHTML =
    `<rect x="${M.l}" y="${M.t}" width="${pw}" height="${ph}" class="ev-black"/>` +
    `<polygon class="ev-white" points="${M.l},${base} ${curve.join(" ")} ${(M.l + pw).toFixed(1)},${base}"/>` +
    axes + phases + `<polyline class="ev-line" points="${curve.join(" ")}"/>` +
    `<g class="ev-dots">${dotStr()}</g>` +
    `<line class="ev-cursor" y1="${M.t}" y2="${M.t + ph}" x1="${M.l}" x2="${M.l}" style="display:none"/>` +
    `<g class="g" style="display:none"><line class="chart-guide" y1="${M.t}" y2="${M.t + ph}"/></g>` +
    `<rect class="ov" x="${M.l}" y="${M.t}" width="${pw}" height="${ph}" fill="transparent" style="cursor:pointer"/>`;

  const ov = svg.querySelector(".ov"), g = svg.querySelector(".g"), gl = g.querySelector("line");
  const cursor = svg.querySelector(".ev-cursor");
  const idxAt = (e) => {
    const r = svg.getBoundingClientRect();
    const px = (e.clientX - r.left) * (W / r.width);
    return Math.max(0, Math.min(n - 1, Math.round(((px - M.l) / pw) * (n - 1))));
  };
  ov.onmousemove = (e) => {
    const i = idxAt(e), p = plies[i], x = xPix(i), r = svg.getBoundingClientRect();
    g.style.display = ""; gl.setAttribute("x1", x); gl.setAttribute("x2", x);
    const san = i > 0 && moves[i - 1] ? moves[i - 1] : "start";
    const ev = (p.cp / 100).toFixed(1);
    const fl = flagAt(i);
    const lab = fl ? ` · <span style="color:${DOT[fl]}">${fl}</span> next: ${esc(moves[i])}` : "";
    tip.innerHTML = `${i ? Math.ceil(i / 2) + "." : ""} ${esc(san)} · <b>${p.cp > 0 ? "+" + ev : ev}</b>${lab}`;
    tip.style.left = (x * (r.width / W)) + "px";
    tip.style.top = (yPix(p.cp) * (r.height / H)) + "px";
    tip.style.opacity = 1;
  };
  ov.onmouseleave = () => { tip.style.opacity = 0; g.style.display = "none"; };
  ov.onclick = (e) => window.dispatchEvent(new CustomEvent("rv-goto", { detail: idxAt(e) }));
  // follow the board: a cursor at the position it shows
  const onPly = (e) => {
    if (!document.body.contains(host)) { window.removeEventListener("rv-ply", onPly); return; }
    const i = +e.detail;
    if (Number.isNaN(i)) return;
    const x = xPix(Math.max(0, Math.min(n - 1, i)));
    cursor.style.display = ""; cursor.setAttribute("x1", x); cursor.setAttribute("x2", x);
  };
  window.addEventListener("rv-ply", onPly);
  const hint = document.createElement("div"); hint.className = "chart-hint";
  hint.textContent = "dots mark where a flagged move was played · click to jump the board there";
  host.appendChild(hint);
}

// ---------------------------------------------------- average eval by move

const CURVE_COLORS = ["#1d6f6a", "#b06a2c", "#7a6f63"];

export function buildEvalCurve(host, groupings, dflt, yLabel) {
  groupings = (groupings || []).filter((gr) => (gr.series || []).some((s) => s.points && s.points.length >= 2));
  if (!groupings.length) return;
  let cur = groupings.find((gr) => gr.key === dflt) || groupings[0];
  let hidden = new Set();
  const bar = document.createElement("div"); bar.className = "chart-toolbar";
  const chart = document.createElement("div"); chart.className = "eval-host";
  groupings.forEach((gr) => {
    const b = document.createElement("button");
    b.className = "gbtn" + (gr === cur ? " on" : "");
    b.textContent = gr.label;
    b.onclick = () => { cur = gr; hidden = new Set(); [...bar.children].forEach((c) => c.classList.toggle("on", c === b)); draw(); };
    bar.appendChild(b);
  });
  host.appendChild(bar); host.appendChild(chart);

  function draw() {
    chart.innerHTML = "";
    const all = cur.series.filter((s) => s.points && s.points.length >= 2);
    const colorOf = (s) => s.color || CURVE_COLORS[all.indexOf(s) % CURVE_COLORS.length];
    const series = all.filter((s) => !hidden.has(s.name));
    const W = host.clientWidth || 880, H = 240;
    const M = { l: 40, r: 12, t: 12, b: 26 };
    const pw = W - M.l - M.r, ph = H - M.t - M.b;
    const xs = series.flatMap((s) => s.points.map((p) => p.x));
    const ys = series.flatMap((s) => s.points.map((p) => p.y));
    const xMin = xs.length ? Math.min(...xs) : 1, xMax = xs.length ? Math.max(...xs) : 2;
    const yAbs = Math.max(0.5, Math.ceil((ys.length ? Math.max(...ys.map(Math.abs)) : 0.5) * 10) / 10 * 1.15);
    const xPix = (x) => M.l + ((x - xMin) / (xMax - xMin || 1)) * pw;
    const yPix = (y) => M.t + ph * (0.5 - Math.max(-yAbs, Math.min(yAbs, y)) / (2 * yAbs));
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.classList.add("evalc");
    const tip = document.createElement("div"); tip.className = "chart-tip";
    let axes = "";
    for (let t = 0; t <= 4; t++) {
      const yv = yAbs - (2 * yAbs * t) / 4, y = yPix(yv).toFixed(1);
      axes += `<line class="${Math.abs(yv) < 1e-9 ? "ev-zero" : "ev-grid"}" x1="${M.l}" y1="${y}" x2="${M.l + pw}" y2="${y}"/>`;
      axes += `<text class="ev-ax" x="${M.l - 5}" y="${(+y + 3).toFixed(1)}" text-anchor="end">${yv > 0 ? "+" + yv.toFixed(1) : yv.toFixed(1)}</text>`;
    }
    for (let t = 0; t <= 6; t++) {
      const xv = Math.round(xMin + ((xMax - xMin) * t) / 6);
      axes += `<text class="ev-ax" x="${xPix(xv).toFixed(1)}" y="${H - 7}" text-anchor="middle">${xv}</text>`;
    }
    const lines = series.map((s) => {
      const pts = s.points.map((p) => `${xPix(p.x).toFixed(1)},${yPix(p.y).toFixed(1)}`).join(" ");
      return `<polyline points="${pts}" fill="none" stroke="${colorOf(s)}" stroke-width="2.2" stroke-linejoin="round"${s.dash ? ' stroke-dasharray="6 4"' : ""}/>`;
    }).join("");
    svg.innerHTML = axes + lines +
      `<g class="g" style="display:none"><line class="chart-guide" y1="${M.t}" y2="${M.t + ph}"/></g>` +
      `<rect class="ov" x="${M.l}" y="${M.t}" width="${pw}" height="${ph}" fill="transparent"/>`;
    const leg = document.createElement("div"); leg.className = "evc-legend";
    leg.innerHTML = all.map((s) =>
      `<button class="evc-key${hidden.has(s.name) ? " off" : ""}" data-name="${esc(s.name)}">` +
      `<span class="evc-sw${s.dash ? " dashed" : ""}" style="${s.dash ? "border-color" : "background"}:${colorOf(s)}"></span>` +
      `${esc(s.name)}${s.games ? ` <span class="evc-n">(${s.games})</span>` : ""}</button>`).join("");
    leg.onclick = (e) => {
      const key = e.target.closest(".evc-key"); if (!key) return;
      const name = key.dataset.name;
      if (!hidden.has(name) && series.length <= 1) return;
      hidden.has(name) ? hidden.delete(name) : hidden.add(name);
      draw();
    };
    chart.append(leg, svg, tip);
    const g = svg.querySelector(".g"), gl = g.querySelector("line");
    svg.querySelector(".ov").onmousemove = (e) => {
      if (!series.length) return;
      const r = svg.getBoundingClientRect();
      const xv = Math.round(xMin + ((e.clientX - r.left) * (W / r.width) - M.l) / pw * (xMax - xMin));
      const x = xPix(xv);
      g.style.display = ""; gl.setAttribute("x1", x); gl.setAttribute("x2", x);
      const parts = series.map((s) => {
        const p = s.points.find((q) => q.x === xv);
        return p ? `<span style="color:${colorOf(s)}">${esc(s.name)} <b>${p.y > 0 ? "+" + p.y : p.y}</b></span>` : null;
      }).filter(Boolean);
      if (!parts.length) { tip.style.opacity = 0; return; }
      tip.innerHTML = `move ${xv} · ` + parts.join(" · ");
      tip.style.left = (x * (r.width / W)) + "px";
      tip.style.top = M.t * (r.height / H) + "px"; tip.style.opacity = 1;
    };
    svg.querySelector(".ov").onmouseleave = () => { tip.style.opacity = 0; g.style.display = "none"; };
  }
  draw();
}
