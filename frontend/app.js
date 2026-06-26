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

  board: (w) => `<figure class="board">${w.svg || ""}` +
    (w.caption ? `<figcaption>${esc(w.caption)}</figcaption>` : "") + `</figure>`,

  eval: (w) => {
    const id = "eval-" + Math.random().toString(36).slice(2);
    pendingEvals.push({ id, plies: w.plies, moves: w.moves });
    return `<div class="eval-host" id="${id}"></div>`;
  },

  movetree: (w) => `<div class="tree">${w.children.map(treeNode).join("")}</div>`,

  // line & recent return placeholders; built/loaded after insertion.
  line: (w) => {
    const id = "chart-" + Math.random().toString(36).slice(2);
    pendingCharts.push({ id, series: w.series });
    return `<div class="chart-host" id="${id}"></div>`;
  },
  recent: () => {
    const id = "recent-" + Math.random().toString(36).slice(2);
    pendingRecents.push(id);
    return `<div id="${id}"></div>`;
  },
  conversion: () => {
    const id = "conv-" + Math.random().toString(36).slice(2);
    pendingConversions.push(id);
    return `<div id="${id}"></div>`;
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
let pendingRecents = [];
let pendingConversions = [];
let pendingEvals = [];
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

// ------------------------------------------------------------- eval chart

const DOT = { inaccuracy: "#e0b020", mistake: "#e08a2b", blunder: "#d0493b" };

function buildEvalChart(host, plies, moves) {
  if (!plies || plies.length < 2) return;
  const W = host.clientWidth || 880, H = 200;
  const M = { l: 8, r: 8, t: 8, b: 8 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;
  const n = plies.length, CLAMP = 1000;
  const clamp = (c) => Math.max(-CLAMP, Math.min(CLAMP, c));
  const xPix = (i) => M.l + (i / (n - 1)) * pw;
  const yPix = (c) => M.t + ph * (0.5 - clamp(c) / (2 * CLAMP));

  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.classList.add("evalc");   // uniform scaling keeps the dots round & responsive
  const tip = document.createElement("div"); tip.className = "chart-tip";
  host.appendChild(svg); host.appendChild(tip);

  const curve = plies.map((p, i) => `${xPix(i).toFixed(1)},${yPix(p.cp).toFixed(1)}`);
  const base = (M.t + ph).toFixed(1);
  const dots = plies.map((p, i) => DOT[p.label]
    ? `<circle cx="${xPix(i).toFixed(1)}" cy="${yPix(p.cp).toFixed(1)}" r="3.2" fill="${DOT[p.label]}"/>`
    : "").join("");

  svg.innerHTML =
    `<rect width="${W}" height="${H}" class="ev-black"/>` +
    `<polygon class="ev-white" points="${M.l},${base} ${curve.join(" ")} ${(M.l + pw).toFixed(1)},${base}"/>` +
    `<line class="ev-mid" x1="${M.l}" y1="${(M.t + ph / 2).toFixed(1)}" x2="${M.l + pw}" y2="${(M.t + ph / 2).toFixed(1)}"/>` +
    `<polyline class="ev-line" points="${curve.join(" ")}"/>` + dots +
    `<g id="g" style="display:none"><line class="chart-guide" y1="${M.t}" y2="${M.t + ph}"/></g>` +
    `<rect id="ov" x="0" y="0" width="${W}" height="${H}" fill="transparent"/>`;

  const ov = svg.querySelector("#ov"), g = svg.querySelector("#g");
  const gl = g.querySelector("line");
  ov.onmousemove = (e) => {
    const r = svg.getBoundingClientRect();
    const px = (e.clientX - r.left) * (W / r.width);
    let i = Math.round(((px - M.l) / pw) * (n - 1));
    i = Math.max(0, Math.min(n - 1, i));
    const p = plies[i], x = xPix(i);
    g.style.display = ""; gl.setAttribute("x1", x); gl.setAttribute("x2", x);
    const moveNo = Math.ceil(i / 2);
    const san = i > 0 && moves[i - 1] ? moves[i - 1] : "start";
    const ev = (p.cp / 100).toFixed(1);
    const evTxt = p.cp > 0 ? "+" + ev : ev;
    const lab = p.label && p.label !== "ok" ? ` · <span style="color:${DOT[p.label]}">${p.label}</span>` : "";
    tip.innerHTML = `${moveNo ? moveNo + "." : ""} ${esc(san)} · <b>${evTxt}</b>${lab}`;
    tip.style.left = (x * (r.width / W)) + "px";
    tip.style.top = (yPix(p.cp) * (r.height / H)) + "px";
    tip.style.opacity = 1;
  };
  ov.onmouseleave = () => { tip.style.opacity = 0; g.style.display = "none"; };
}

// ------------------------------------------------------------- recent games

function initRecent(host) {
  let n = 10;
  const bar = document.createElement("div"); bar.className = "chart-toolbar";
  const body = document.createElement("div");
  [["5", 5], ["10", 10], ["20", 20], ["All", 0]].forEach(([lbl, val]) => {
    const b = document.createElement("button");
    b.className = "gbtn" + (val === n ? " on" : "");
    b.textContent = lbl;
    b.onclick = () => { n = val; [...bar.children].forEach((c) => c.classList.toggle("on", c === b)); load(); };
    bar.appendChild(b);
  });
  host.appendChild(bar); host.appendChild(body);

  async function load() {
    body.innerHTML = `<p class="text"><span class="spinner"></span>Analysing games… first run can take a while (results are cached).</p>`;
    try {
      const meta = state.doc.meta;
      const d = await getJSON(`/api/recent?user=${encodeURIComponent(meta.player)}` +
        `&format=${meta.format || ""}&n=${n}`);
      renderRecent(body, d);
    } catch (e) {
      body.innerHTML = `<p class="text" style="color:var(--loss)">${esc(e.message)}</p>`;
    }
  }
  load();
}

function renderRecent(body, d) {
  const thr = (d.threshold / 100).toFixed(1);
  const cols = ["", "Date", "Opponent", "Result", "Accuracy", "Blunders", `Conversion (±${thr})`];
  const head = cols.map((c) => `<th>${esc(c)}</th>`).join("");
  const rows = d.games.map((g) => {
    const res = g.outcome === "win" ? "✓" : g.outcome === "loss" ? "✗" : "=";
    const resCls = g.outcome === "win" ? "res-win" : g.outcome === "loss" ? "res-loss" : "";
    const acc = g.accuracy != null ? Math.round(g.accuracy) + "%" : "—";
    let conv = "—";
    if (g.decisive) {
      const cls = g.decisive.held ? "conv-held" : "conv-lost";
      const tick = g.decisive.held ? "✓ held" : "✗ lost";
      conv = `move ${g.decisive.move} <span class="${cls}">${tick}</span>`;
    }
    return `<tr class="rrow" data-id="${g.id}">` +
      `<td class="${resCls}">${res}</td><td>${esc(g.date)}</td>` +
      `<td>${esc(g.opponent)} (${g.opp_elo || "?"})</td><td>${g.result}</td>` +
      `<td>${acc}</td><td>${g.blunders}</td><td>${conv}</td></tr>`;
  }).join("");
  body.innerHTML = `<table class="recent-tbl"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
  body.querySelectorAll(".rrow").forEach((tr) => { tr.onclick = () => gotoGame(tr.dataset.id); });
}

async function initConversion(host) {
  host.innerHTML = `<p class="text"><span class="spinner"></span>Analysing all games (cached after first run)…</p>`;
  try {
    const meta = state.doc.meta;
    const d = await getJSON(`/api/conversion?user=${encodeURIComponent(meta.player)}` +
      `&format=${meta.format || ""}`);
    host.innerHTML = d.sections.map((s) =>
      `<h3>${esc(s.title)}</h3>` + s.widgets.map(renderWidget).join("")).join("");
  } catch (e) {
    host.innerHTML = `<p class="text" style="color:var(--loss)">${esc(e.message)}</p>`;
  }
}

async function gotoGame(id) {
  state.mode = "game"; renderTabs(); renderControls();
  setStatus("Running Stockfish… first analysis can take a few seconds.", false, true);
  try {
    state.doc = await getJSON(`/api/game?selector=${encodeURIComponent(id)}&depth=${state.cfg.depth}`);
    state.hidden = new Set(); $("chips").innerHTML = "";
    renderSections(); setStatus("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) { setStatus(e.message, true); }
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
  pendingRecents = [];
  pendingConversions = [];
  pendingEvals = [];
  const doc = state.doc;
  const html = doc.sections.filter((s) => !state.hidden.has(s.title)).map((s) =>
    (s.title ? `<h2>${esc(s.title)}</h2>` : "") + s.widgets.map(renderWidget).join("")
  ).join("");
  const link = doc.meta && doc.meta.url ?
    ` <a href="${doc.meta.url}" target="_blank" rel="noopener">↗</a>` : "";
  $("result").innerHTML = `<h1>${esc(doc.title)}${link}</h1>` +
    (doc.subtitle ? `<p class="sub-title">${esc(doc.subtitle)}</p>` : "") + html;
  document.title = doc.title + " · Chess Analyzer";
  pendingCharts.forEach((c) => initChart($(c.id), c.series));
  pendingRecents.forEach((id) => initRecent($(id)));
  pendingConversions.forEach((id) => initConversion($(id)));
  pendingEvals.forEach((e) => buildEvalChart($(e.id), e.plies, e.moves));
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
  let url, busy;
  if (state.mode === "player") {
    url = `/api/player?user=${encodeURIComponent($("f-user").value.trim())}&format=${$("f-fmt").value}`;
    busy = "Building report…";
  } else if (state.mode === "game") {
    url = `/api/game?selector=${encodeURIComponent($("f-game").value)}&depth=${$("f-depth").value}`;
    busy = "Running Stockfish… first analysis can take a few seconds.";
  } else {
    url = `/api/compare?a=${encodeURIComponent($("f-a").value.trim())}&b=${encodeURIComponent($("f-b").value.trim())}`;
    busy = "Comparing…";
  }
  setStatus(busy, false, true);
  try {
    state.doc = await getJSON(url);
    state.hidden = new Set();
    if (state.mode === "player") renderChips(); else $("chips").innerHTML = "";
    renderSections(); setStatus("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) { setStatus(e.message, true); }
  finally { $("run").disabled = false; }
}

// ----------------------------------------------------------------------- init

function renderTabs() {
  $("tabs").innerHTML = state.cfg.modes.map((m) =>
    `<button class="tab ${m === state.mode ? "active" : ""}" data-mode="${m}">${MODE_LABELS[m] || m}</button>`).join("");
  document.querySelectorAll(".tab").forEach((b) => {
    b.onclick = () => { state.mode = b.dataset.mode; renderTabs(); renderControls(); };
  });
}

async function syncGames() {
  const btn = $("sync");
  btn.disabled = true;
  setStatus("Syncing from Chess.com…", false, true);
  try {
    const r = await fetch("/api/scrape?user=" + encodeURIComponent(state.cfg.user || ""),
      { method: "POST" });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || `HTTP ${r.status}`);
    const skip = d.skipped ? `, ${d.skipped} months already up to date` : "";
    setStatus(`Synced: ${d.new} new game${d.new === 1 ? "" : "s"}${skip}.`);
  } catch (e) {
    setStatus("Sync failed: " + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

(async function init() {
  try { state.cfg = await getJSON("/api/config"); }
  catch (e) { setStatus("Backend not reachable: " + e.message, true); return; }
  renderTabs(); renderControls();
  $("sync").onclick = syncGames;
})();
