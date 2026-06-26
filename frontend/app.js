"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const state = { cfg: null, mode: "player", doc: null, hidden: new Set() };
const MODE_LABELS = { player: "Player report", game: "Game review", compare: "Compare" };
const FORMATS = ["bullet", "blitz", "rapid"];

async function getJSON(url) {
  const r = await fetch(url);
  const d = await r.json();
  if (!r.ok || d.error) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}
function setStatus(msg, isErr = false, busy = false) {
  const s = $("status");
  s.className = "status" + (isErr ? " err" : "");
  s.innerHTML = busy ? `<span class="spinner"></span>${esc(msg)}` : (msg ? esc(msg) : "");
}

// ---------------------------------------------------------------- widgets (JS)

const pct = (n, t) => (t ? Math.round((100 * n) / t) + "%" : "—");

function wBar(w, d, l) {
  const t = w + d + l; if (!t) return "";
  const p = (x) => (100 * x) / t;
  return `<div class="bar"><span class="w" style="width:${p(w)}%"></span>` +
    `<span class="d" style="width:${p(d)}%"></span>` +
    `<span class="l" style="width:${p(l)}%"></span></div>`;
}
function cell(c) {
  return (c && typeof c === "object" && "bar" in c) ? wBar(...c.bar) : esc(c);
}

const WIDGETS = {
  cards: (w) => `<div class="cards">` + w.items.map((it) =>
    `<div class="card"><div class="big">${esc(it.value)}</div>` +
    `<div class="lbl">${esc(it.label)}</div>` +
    (it.sub ? `<div class="sub">${esc(it.sub)}</div>` : "") + `</div>`).join("") + `</div>`,

  table: (w) => `<table><thead><tr>` + w.columns.map((c) => `<th>${esc(c)}</th>`).join("") +
    `</tr></thead><tbody>` + w.rows.map((r) =>
      `<tr>` + r.map((c) => `<td>${cell(c)}</td>`).join("") + `</tr>`).join("") + `</tbody></table>`,

  wdl_table: (w) => {
    const head = [w.label_col, "Games", "W", "D", "L", "Win%", ""]
      .map((c) => `<th>${esc(c)}</th>`).join("");
    const body = w.rows.map((r) => {
      const t = r.win + r.draw + r.loss;
      return `<tr>` + [r.label, t, r.win, r.draw, r.loss, pct(r.win, t), wBar(r.win, r.draw, r.loss)]
        .map((c, i) => `<td>${i === 6 ? c : esc(c)}</td>`).join("") + `</tr>`;
    }).join("");
    return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  },

  ranking: (w) => {
    const items = w.rows.map((r, i) =>
      `<li><span class="rk-rank">${i + 1}</span>` +
      `<span class="rk-label">${esc(r.label)}</span>` +
      (r.sub ? `<span class="rk-sub">${esc(r.sub)}</span>` : "") +
      `<span class="rk-val">${esc(r.value)}</span></li>`).join("");
    return `<div class="ranking">${w.title ? `<h3>${esc(w.title)}</h3>` : ""}<ol>${items}</ol></div>`;
  },

  group: (w) => `<div class="group group-${w.layout || "row"}">` +
    w.widgets.map(renderWidget).join("") + `</div>`,

  text: (w) => `<p class="text">${esc(w.body)}</p>`,

  movetree: (w) => `<div class="tree">${w.children.map(treeNode).join("")}</div>`,

  // line is special: returns a placeholder; the chart is built after insertion.
  line: (w) => {
    const id = "chart-" + Math.random().toString(36).slice(2);
    pendingCharts.push({ id, series: w.series });
    return `<div class="chart-host" id="${id}"></div>`;
  },
};

function treeNode(node) {
  const wr = (node.w + node.d + node.l)
    ? Math.round((100 * node.w) / (node.w + node.d + node.l)) + "%" : "";
  const head = `<span class="mv">${esc(node.move)}</span>` +
    `<span class="ct">${node.count}</span>${wBar(node.w, node.d, node.l)}` +
    `<span class="wr">${wr}</span>`;
  const cls = node.mine ? "mine" : "opp";
  if (node.children && node.children.length) {
    return `<details class="${cls}"><summary>${head}</summary>` +
      `<div class="kids">${node.children.map(treeNode).join("")}</div></details>`;
  }
  return `<div class="leaf ${cls}">${head}</div>`;
}

let pendingCharts = [];
function renderWidget(w) {
  const fn = WIDGETS[w.type];
  return fn ? fn(w) : `<!-- ${w.type} -->`;
}

// ---------------------------------------------------------- interactive chart

function buildRatingChart(host, series) {
  const pts = (series[0] && series[0].points) || [];
  const data = pts.map((p, i) => ({ i, date: p.x, y: p.y }));
  if (data.length < 2) return;
  const W = host.clientWidth || 880, H = 280;
  const M = { l: 46, r: 14, t: 12, b: 26 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;
  const n = data.length;
  let dom = [0, n - 1], curYd = [0, 1], brushing = false, startX = 0;

  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const tip = document.createElement("div"); tip.className = "chart-tip";
  host.appendChild(svg); host.appendChild(tip);

  const visible = () => data.filter((d) => d.i >= Math.ceil(dom[0]) && d.i <= Math.floor(dom[1]));
  const xPix = (i) => M.l + ((i - dom[0]) / (dom[1] - dom[0])) * pw;
  const yPix = (v) => M.t + (1 - (v - curYd[0]) / (curYd[1] - curYd[0])) * ph;
  const toVbX = (e) => { const r = svg.getBoundingClientRect(); return (e.clientX - r.left) * (W / r.width); };

  function draw() {
    const vs = visible();
    let lo = Math.min(...vs.map((d) => d.y)), hi = Math.max(...vs.map((d) => d.y));
    if (lo === hi) { lo -= 10; hi += 10; }
    const pad = (hi - lo) * 0.12 || 8; curYd = [lo - pad, hi + pad];
    let s = "";
    for (let t = 0; t <= 4; t++) {
      const val = curYd[0] + ((curYd[1] - curYd[0]) * t) / 4, y = yPix(val);
      s += `<line class="chart-grid" x1="${M.l}" y1="${y.toFixed(1)}" x2="${W - M.r}" y2="${y.toFixed(1)}"/>`;
      s += `<text x="${M.l - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end">${Math.round(val)}</text>`;
    }
    const ticks = 5;
    for (let t = 0; t <= ticks; t++) {
      const idx = Math.round(dom[0] + ((dom[1] - dom[0]) * t) / ticks), d = data[idx];
      if (d) s += `<text x="${xPix(idx).toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(d.date.slice(5))}</text>`;
    }
    const pp = vs.map((d) => `${xPix(d.i).toFixed(1)},${yPix(d.y).toFixed(1)}`);
    if (pp.length) {
      const base = (M.t + ph).toFixed(1);
      s += `<polygon class="chart-area" points="${xPix(vs[0].i).toFixed(1)},${base} ${pp.join(" ")} ${xPix(vs[vs.length - 1].i).toFixed(1)},${base}"/>`;
      s += `<polyline class="chart-line" points="${pp.join(" ")}"/>`;
    }
    s += `<g id="guide" style="display:none"><line class="chart-guide" y1="${M.t}" y2="${M.t + ph}"/>` +
      `<circle class="chart-dot" r="4"/></g>`;
    s += `<rect id="brush" class="chart-brush" y="${M.t}" height="${ph}" width="0" style="display:none"/>`;
    s += `<rect id="ov" x="${M.l}" y="${M.t}" width="${pw}" height="${ph}" fill="transparent"/>`;
    svg.innerHTML = s;
    bindOverlay();
  }

  function bindOverlay() {
    const ov = svg.querySelector("#ov"), guide = svg.querySelector("#guide");
    const gl = guide.querySelector("line"), dot = guide.querySelector("circle");
    const brush = svg.querySelector("#brush");
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
      const x = xPix(idx), y = yPix(d.y);
      guide.style.display = ""; gl.setAttribute("x1", x); gl.setAttribute("x2", x);
      dot.setAttribute("cx", x); dot.setAttribute("cy", y);
      const prev = data[idx - 1], ch = prev ? d.y - prev.y : null;
      const chTxt = ch === null ? "" : ch >= 0 ?
        `<span class="up">▲ +${ch}</span>` : `<span class="dn">▼ ${ch}</span>`;
      tip.innerHTML = `${esc(d.date)} · <b>${d.y}</b> ${chTxt}`;
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
      let ns = Math.max(4, Math.min(n - 1, span * (e.deltaY < 0 ? 0.8 : 1.25)));
      let a = center - (center - dom[0]) * (ns / span), b = a + ns;
      a = Math.max(0, a); b = Math.min(n - 1, b);
      if (b - a >= 3) { dom = [a, b]; draw(); }
    };
  }

  window.addEventListener("mouseup", (e) => {
    if (!brushing) return; brushing = false;
    const brush = svg.querySelector("#brush"); if (brush) brush.style.display = "none";
    const x0 = Math.min(startX, toVbX(e)), x1 = Math.max(startX, toVbX(e));
    if (x1 - x0 > 6) {
      let a = Math.floor(dom[0] + ((x0 - M.l) / pw) * (dom[1] - dom[0]));
      let b = Math.ceil(dom[0] + ((x1 - M.l) / pw) * (dom[1] - dom[0]));
      a = Math.max(0, a); b = Math.min(n - 1, b);
      if (b - a >= 1) { dom = [a, b]; draw(); }
    }
  });
  svg.addEventListener("dblclick", () => { dom = [0, n - 1]; draw(); });
  draw();
}

// Closing rating per period (points are chronological, so last write wins).
function aggregate(points, gran) {
  if (gran === "game") return points;
  const key = gran === "month" ? (x) => x.slice(0, 7) : (x) => x;
  const m = new Map();
  for (const p of points) m.set(key(p.x), { x: key(p.x), y: p.y });
  return [...m.values()];
}

function initChart(host, series) {
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
    buildRatingChart(wrap, [{ name: series[0].name, points: aggregate(series[0].points, gran) }]);
  }
  render();
}

// ----------------------------------------------------------------- rendering

function renderSections() {
  pendingCharts = [];
  const doc = state.doc;
  const html = doc.sections.filter((s) => !state.hidden.has(s.title)).map((s) =>
    (s.title ? `<h2>${esc(s.title)}</h2>` : "") + s.widgets.map(renderWidget).join("")
  ).join("");
  const link = doc.meta && doc.meta.url ?
    ` <a href="${doc.meta.url}" target="_blank" rel="noopener">↗</a>` : "";
  $("result").innerHTML = `<h1>${esc(doc.title)}${link}</h1>` +
    (doc.subtitle ? `<p class="sub-title">${esc(doc.subtitle)}</p>` : "") + html;
  pendingCharts.forEach((c) => initChart($(c.id), c.series));
}

function renderChips() {
  const doc = state.doc;
  if (!doc || state.mode !== "player") { $("chips").innerHTML = ""; return; }
  const chips = doc.sections.filter((s) => s.title).map((s) => {
    const on = !state.hidden.has(s.title);
    return `<button class="chip ${on ? "on" : ""}" data-sec="${esc(s.title)}">${esc(s.title)}</button>`;
  }).join("");
  $("chips").innerHTML = `<span class="lead">Show</span>` + chips;
  $("chips").querySelectorAll(".chip").forEach((b) => {
    b.onclick = () => {
      const t = b.dataset.sec;
      state.hidden.has(t) ? state.hidden.delete(t) : state.hidden.add(t);
      renderChips(); renderSections();
    };
  });
}

// --------------------------------------------------------------- controls/run

function field(label, inner) { return `<div class="field"><label>${label}</label>${inner}</div>`; }

function renderControls() {
  const c = $("controls"), user = state.cfg.user || "";
  $("chips").innerHTML = ""; $("result").innerHTML = ""; setStatus("");
  if (state.mode === "player") {
    const opts = FORMATS.map((f) =>
      `<option value="${f}">${f[0].toUpperCase() + f.slice(1)}</option>`).join("");
    c.innerHTML = field("Username", `<input id="f-user" value="${esc(user)}">`) +
      field("Format", `<select id="f-fmt">${opts}</select>`) +
      `<button class="go" id="run">Show stats</button>`;
    $("f-fmt").value = "rapid";
  } else if (state.mode === "game") {
    c.innerHTML = field("Game", `<select class="wide" id="f-game"><option value="last">Loading…</option></select>`) +
      field("Engine depth", `<input id="f-depth" type="number" min="6" max="22" value="${state.cfg.depth}">`) +
      `<button class="go" id="run">Analyze</button>`;
    loadGames();
  } else {
    c.innerHTML = field("Player A", `<input id="f-a" value="${esc(user)}">`) +
      field("Player B", `<input id="f-b" placeholder="opponent">`) +
      `<button class="go" id="run">Compare</button>`;
  }
  $("run").onclick = run;
}

async function loadGames() {
  try {
    const games = await getJSON("/api/games?user=" + encodeURIComponent(state.cfg.user || ""));
    $("f-game").innerHTML = [`<option value="last">⭐ Most recent</option>`].concat(
      games.map((g) => {
        const m = g.outcome === "win" ? "✓" : g.outcome === "loss" ? "✗" : "=";
        return `<option value="${g.id}">${m} ${g.date} · ${esc(g.white)} vs ${esc(g.black)} (${g.result}) · ${g.time_class}</option>`;
      })).join("");
  } catch (e) { setStatus("Could not load games: " + e.message, true); }
}

async function run() {
  $("run").disabled = true;
  try {
    if (state.mode === "player") {
      setStatus("Building report…", false, true);
      const doc = await getJSON(`/api/player?user=${encodeURIComponent($("f-user").value.trim())}` +
        `&format=${$("f-fmt").value}`);
      state.doc = doc; state.hidden = new Set();
      renderChips(); renderSections(); setStatus("");
    } else if (state.mode === "game") {
      setStatus("Running Stockfish… first analysis can take a few seconds.", false, true);
      const d = await getJSON(`/api/game?selector=${encodeURIComponent($("f-game").value)}&depth=${$("f-depth").value}`);
      injectHTML(d); setStatus("");
    } else {
      setStatus("Comparing…", false, true);
      const d = await getJSON(`/api/compare?a=${encodeURIComponent($("f-a").value.trim())}&b=${encodeURIComponent($("f-b").value.trim())}`);
      injectHTML(d); setStatus("");
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) { setStatus(e.message, true); }
  finally { $("run").disabled = false; }
}

function injectHTML(d) {
  const link = d.meta && d.meta.url ? ` <a href="${d.meta.url}" target="_blank" rel="noopener">↗</a>` : "";
  $("result").innerHTML = `<h1>${esc(d.title)}${link}</h1>` +
    (d.subtitle ? `<p class="sub-title">${esc(d.subtitle)}</p>` : "") + d.html;
  document.title = d.title + " · Chess Analyzer";
}

// ----------------------------------------------------------------------- init

function renderTabs() {
  $("tabs").innerHTML = state.cfg.modes.map((m) =>
    `<button class="tab ${m === state.mode ? "active" : ""}" data-mode="${m}">${MODE_LABELS[m] || m}</button>`).join("");
  document.querySelectorAll(".tab").forEach((b) => {
    b.onclick = () => { state.mode = b.dataset.mode; renderTabs(); renderControls(); };
  });
}

(async function init() {
  try { state.cfg = await getJSON("/api/config"); }
  catch (e) { setStatus("Backend not reachable: " + e.message, true); return; }
  renderTabs(); renderControls();
})();
