// Widget renderers: one per `type` in chessanalysis/widgets.py.
//
// A renderer returns HTML. Anything that needs the element in the page first
// (charts, the board) registers a callback on `ctx.after`, run once the HTML
// is inserted.

import { esc, getJSON, resultCls, resultMark, spinner, errorBox, who } from "./api.js";
import { buildEvalChart, buildEvalCurve, buildRatingChart, initChart, initVariantChart } from "./charts.js";
import { buildReviewBoard } from "./review.js";

let uid = 0;
const nextId = (p) => `${p}-${++uid}`;

function wBar(w, d, l) {
  const t = w + d + l; if (!t) return "";
  const p = (x) => (100 * x) / t;
  return `<div class="bar"><span class="w" style="width:${p(w)}%"></span>` +
    `<span class="d" style="width:${p(d)}%"></span><span class="l" style="width:${p(l)}%"></span></div>`;
}
function cell(c) { return (c && typeof c === "object" && "bar" in c) ? wBar(...c.bar) : esc(c); }

function gameRows(games) {
  return games.map((g) =>
    `<tr class="rrow" data-game-id="${esc(g.id)}" data-ply="${g.ply ?? ""}">` +
    `<td class="${resultCls(g.outcome)}">${resultMark(g.outcome)}</td><td>${esc(g.date)}</td>` +
    `<td>${esc(g.opponent || "?")}${g.opp_elo ? ` (${g.opp_elo})` : ""}</td>` +
    `<td class="reason-note">${esc(g.note || g.detail || "")}</td></tr>`).join("");
}

const R = {
  cards: (w) => `<div class="cards">` + w.items.map((it) =>
    `<div class="card"><div class="big">${esc(it.value)}</div><div class="lbl">${esc(it.label)}</div>` +
    (it.sub ? `<div class="sub">${esc(it.sub)}</div>` : "") + `</div>`).join("") + `</div>`,

  table: (w) => `<div class="tablewrap"><table><thead><tr>` + w.columns.map((c) => `<th>${esc(c)}</th>`).join("") +
    `</tr></thead><tbody>` + w.rows.map((r) => `<tr>` + r.map((c) => `<td>${cell(c)}</td>`).join("") + `</tr>`).join("") +
    `</tbody></table></div>`,

  drilltable: (w) => {
    const head = `<th></th>` + w.columns.map((c) => `<th>${esc(c)}</th>`).join("");
    const body = w.rows.map((r, i) => {
      const games = r.games || [], has = games.length > 0;
      const main = `<tr class="dt-row${has ? " dt-open" : ""}" data-row="${i}"><td class="dt-caret">${has ? "▸" : ""}</td>` +
        r.cells.map((c) => `<td>${cell(c)}</td>`).join("") + `</tr>`;
      const sub = has ? `<tr class="dt-games" data-for="${i}" hidden><td colspan="${w.columns.length + 1}">` +
        `<table class="recent-tbl reason-games"><tbody>${gameRows(games)}</tbody></table></td></tr>` : "";
      return main + sub;
    }).join("");
    return `<div class="tablewrap"><table class="drilltable"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  },

  text: (w) => `<p class="text">${esc(w.body)}` +
    (w.link ? ` <a class="guide-link" href="${esc(w.link.route)}">${esc(w.link.label)} →</a>` : "") + `</p>`,

  actions: (w) => `<div class="actions">` + w.items.map((a) =>
    `<a class="btn" href="${esc(a.route)}">${esc(a.label)} →</a>`).join("") + `</div>`,

  focus: (w) => `<div class="focus">` + w.items.map((it) =>
    `<div class="fc ${esc(it.tone)}"><div class="fc-title">${esc(it.title)}</div>` +
    `<div class="fc-body">${esc(it.body)}</div>` +
    (it.action ? `<a class="btn${it.tone === "leak" || it.tone === "info" ? " primary" : ""}" href="${esc(it.action.route)}">${esc(it.action.label)} →</a>` : "") +
    `</div>`).join("") + `</div>`,

  moments: (w) => `<div class="moments">` + w.items.map((m) =>
    `<span class="mo${m.mine ? "" : " theirs"}" data-goto="${m.ply}" title="${m.mine ? "your move" : "their move"}">` +
    `<i style="background:var(--${m.kind === "blunder" ? "blun" : m.kind === "mistake" ? "mist" : "inacc"})"></i>` +
    `<b>${esc(m.label)}</b><span class="mut">${esc(m.note)}</span></span>`).join("") + `</div>`,

  verdict: (w) => {
    const opts = w.options.map((o) =>
      `<option value="${esc(o.key)}"${o.key === w.primary ? " selected" : ""}>${esc(o.label)}</option>`).join("");
    const manual = w.manual ? `<span class="vd-manual">manually set</span>` : "";
    const cheat = w.cheated ? `<div class="vd-cheat">⚑ Not counted: ${esc(w.cheated)}. Any rating this game cost you has been added back.</div>` : "";
    return `<div class="verdict${w.anomalous || w.cheated ? " vd-anomalous" : ""}" data-game-id="${esc(w.game_id)}">${cheat}` +
      `<div class="vd-top"><div class="vd-main"><div class="vd-label">${esc(w.label)}</div>` +
      `<div class="vd-headline">${esc(w.headline)}</div>${w.sub ? `<div class="vd-sub">${esc(w.sub)}</div>` : ""}</div>` +
      `<label class="vd-pick">reason${manual}<select class="vd-select">${opts}</select>` +
      `<span class="vd-flag" title="Excluded from every statistic; still listed in the history.">` +
      `<input type="checkbox" class="vd-anom"${w.anomalous ? " checked" : ""}>anomalous — don't count</span></label>` +
      `</div><p class="text vd-detail">${esc(w.detail)}</p></div>`;
  },

  barstack: (w) => {
    const pal = w.palette;
    const order = (w.rows[0] && w.rows[0].segments.map((s) => s.name)) || Object.keys(pal);
    const legend = [...new Set([...order, ...Object.keys(pal)])].filter((k) => w.rows.some((r) => r.segments.some((s) => s.name === k && s.value)))
      .map((k) => `<span class="bs-leg"><i style="background:${pal[k]}"></i>${esc(k)}</span>`).join("");
    const rows = w.rows.map((r) => {
      const total = r.segments.reduce((s, seg) => s + seg.value, 0) || 1;
      const segs = r.segments.filter((s) => s.value > 0).map((s) => {
        const pc = 100 * s.value / total;
        return `<span class="bs-seg" style="width:${pc.toFixed(1)}%;background:${pal[s.name] || "#ccc"}" ` +
          `title="${esc(s.name)}: ${s.value}">${pc > 7 ? s.value : ""}</span>`;
      }).join("");
      return `<div class="bs-row"><span class="bs-label">${esc(r.label)}</span><span class="bs-bar">${segs}</span>` +
        (r.note ? `<span class="bs-note">${esc(r.note)}</span>` : "") + `</div>`;
    }).join("");
    return `<div class="barstack">${w.title ? `<div class="bs-title">${esc(w.title)}</div>` : ""}${rows}` +
      `<div class="bs-legend">${legend}</div></div>`;
  },

  timeline: (w) => {
    const col = { win: "var(--win)", draw: "var(--draw)", loss: "var(--loss)" };
    const cells = w.items.map((it) => it.id
      ? `<a class="tl-cell" href="#/game/${esc(it.id)}" style="background:${col[it.outcome] || "#ccc"}" title="${esc(it.label || "")}"></a>`
      : `<span class="tl-cell" style="background:${col[it.outcome] || "#ccc"}" title="${esc(it.label || "")}"></span>`).join("");
    return `<div class="timeline">${w.title ? `<div class="bs-title">${esc(w.title)}</div>` : ""}<div class="tl-row">${cells}</div></div>`;
  },

  reasons: (w) => `<div class="reasons"><div class="reasons-head">${esc(w.label)}</div>` + w.groups.map((gr) =>
    `<details class="reason"><summary><span class="reason-label">${esc(gr.label)}</span>` +
    `<span class="reason-count">${gr.count}</span><span class="reason-sub">${esc(gr.sub || "")}</span></summary>` +
    (gr.stat ? `<div class="reason-stat">${esc(gr.stat)}</div>` : "") +
    (gr.games && gr.games.length ? `<table class="recent-tbl reason-games"><tbody>${gameRows(gr.games)}</tbody></table>` : "") +
    `</details>`).join("") + `</div>`,

  gapchart: (w, ctx) => {
    const id = nextId("gap");
    ctx.after.push(() => buildGapChart(document.getElementById(id), w));
    return `<div id="${id}"></div>`;
  },

  line: (w, ctx) => {
    const id = nextId("chart");
    ctx.after.push(() => {
      const host = document.getElementById(id);
      if (w.variants) initVariantChart(host, w.variants, w.y_max ?? null, w.games || null);
      else if (w.toolbar !== false) initChart(host, w.series, w.agg || "last", !!w.ma, w.y_max ?? null);
      else buildRatingChart(host, w.series, !!w.ma, w.y_max ?? null);
    });
    return `<div class="chart-host" id="${id}"></div>`;
  },

  xyline: (w) => xyline(w),

  eval: (w, ctx) => {
    const id = nextId("eval");
    ctx.after.push(() => buildEvalChart(document.getElementById(id), w.plies, w.moves, w.me, w.division));
    return `<div class="eval-host" id="${id}"></div>`;
  },

  evalcurve: (w, ctx) => {
    const id = nextId("evc");
    ctx.after.push(() => buildEvalCurve(document.getElementById(id), w.groupings, w.default, w.y_label));
    return `<div class="eval-host" id="${id}"></div>`;
  },

  review: (w, ctx) => {
    const id = nextId("rv");
    ctx.after.push(() => buildReviewBoard(document.getElementById(id), w));
    return `<div class="review-host" id="${id}"></div>`;
  },

  // the engine insights section of Stats: fetched lazily, it runs the engine
  conversion: (w, ctx) => {
    const id = nextId("insights");
    ctx.after.push(() => initInsights(document.getElementById(id)));
    return `<div id="${id}"></div>`;
  },
};

export function renderWidget(w, ctx) {
  const fn = R[w.type];
  return fn ? fn(w, ctx) : `<!-- ${esc(w.type)} -->`;
}

export function renderWidgets(widgets) {
  const ctx = { after: [] };
  const html = widgets.map((w) => renderWidget(w, ctx)).join("");
  return { html, after: ctx.after };
}

// Render a Document's sections into `host`. `category` filters to one
// category; categories get a heading of their own.
export function renderDoc(host, doc, { category = null, head = true } = {}) {
  const ctx = { after: [] };
  const sec = (s) => (s.title ? `<h2>${esc(s.title)}</h2>` : "") + s.widgets.map((w) => renderWidget(w, ctx)).join("");
  const cats = [];
  for (const s of doc.sections) if (s.category && !cats.includes(s.category)) cats.push(s.category);
  let html = "";
  if (cats.length) {
    html = cats.filter((c) => !category || c === category).map((c) =>
      `<div class="cat-head">${esc(c)}</div>` + doc.sections.filter((s) => s.category === c).map(sec).join("")).join("");
    if (!category) html += doc.sections.filter((s) => !s.category).map(sec).join("");
  } else {
    html = doc.sections.map(sec).join("");
  }
  const link = doc.meta && doc.meta.url ? ` <a href="${esc(doc.meta.url)}" target="_blank" rel="noopener">↗ chess.com</a>` : "";
  host.innerHTML = (head ? `<h1>${esc(doc.title)}${link}</h1>` +
    (doc.subtitle ? `<p class="sub-title">${esc(doc.subtitle)}</p>` : "") : "") + html;
  ctx.after.forEach((f) => f());
  return cats;
}

// ------------------------------------------------------------- gap chart

function buildGapChart(host, w) {
  const variants = w.variants || [{ label: "", rows: w.rows }];
  let cur = variants[0];
  const open = new Set();
  const words = (v) => `${Math.abs(100 * v).toFixed(0)}% ${v >= 0 ? "more" : "less"}`;
  function draw() {
    const rows = cur.rows;
    // the scale fits the gaps, not the widest range: one thin row's ±150%
    // range would otherwise flatten every other row. A range that runs past
    // the edge ends in an arrow, and its numbers are on the row.
    const ext = Math.max(0.2, ...rows.map((r) => Math.abs(r.gap) * 1.6), ...rows.map((r) =>
      Math.min(0.4, Math.max(Math.abs(r.lo), Math.abs(r.hi)))));
    const span = Math.min(0.6, Math.ceil(ext * 10) / 10);
    const x = (v) => 50 + (50 * Math.max(-span, Math.min(span, v))) / span;
    let html = "", group = null;
    if (variants.length > 1) {
      html += `<div class="chart-toolbar">` + variants.map((v, i) =>
        `<button class="gbtn${v === cur ? " on" : ""}" data-v="${i}">${esc(v.label)}</button>`).join("") + `</div>`;
    }
    for (const r of rows) {
      if (r.group !== group) { group = r.group; html += `<div class="gc-group">${esc(group)}</div>`; }
      const a = x(Math.min(0, r.gap)), b = x(Math.max(0, r.gap));
      // a range over 100 points wide says nothing yet, whichever way the bar points
      const tag = r.verdict === "leak" ? "weakness" : r.verdict === "strength" ? "strength"
        : r.hi - r.lo > 1 ? "too few moves" : "unclear";
      const range = `95% range: ${words(r.lo)} to ${words(r.hi)}`;
      const clipLo = r.lo < -span ? `<span class="gc-clip l">◂</span>` : "";
      const clipHi = r.hi > span ? `<span class="gc-clip r">▸</span>` : "";
      html += `<div class="gc-row ${r.verdict}${open.has(r.key) ? " open" : ""}" data-key="${esc(r.key)}" title="${esc(range)}">` +
        `<span class="gc-label">${esc(r.label)}${r.moves != null ? `<span class="gc-n">${r.moves} moves</span>` : ""}</span>` +
        `<span class="gc-track"><span class="gc-axis"></span>` +
        `<span class="gc-ci" style="left:${x(r.lo)}%;width:${Math.max(0.5, x(r.hi) - x(r.lo))}%"></span>${clipLo}${clipHi}` +
        `<span class="gc-bar" style="left:${a}%;width:${Math.max(0.6, b - a)}%"></span></span>` +
        `<span class="gc-val">${words(r.gap)}</span>` +
        `<span class="gc-tag">${tag}</span>` +
        `<div class="gc-detail">${esc(r.help || "")} ${esc(r.detail || range + ".")}</div></div>`;
    }
    html += `<div class="gc-scale"><div></div><div><span>← loses less · better</span>` +
      `<span>same as players at your rating</span><span>worse · loses more →</span></div><div></div><div></div></div>`;
    if (w.note) html += `<div class="gc-note">${esc(w.note)} Click a row for the numbers behind it.</div>`;
    host.innerHTML = `<div class="gapchart">${html}</div>`;
    host.querySelectorAll("[data-v]").forEach((b) => { b.onclick = () => { cur = variants[+b.dataset.v]; draw(); }; });
    host.querySelectorAll(".gc-row").forEach((el) => {
      el.onclick = () => { const k = el.dataset.key; open.has(k) ? open.delete(k) : open.add(k); draw(); };
    });
  }
  draw();
}

// ------------------------------------------------------------- xy line (bands)

function xyline(w) {
  const CW = 720, CH = 250, P = { l: 46, r: 118, t: 12, b: 32 };
  const all = w.series.flatMap((s) => s.points || []);
  if (!all.length) return "";
  const xs = all.map((p) => p.x), ys = all.map((p) => p.y);
  let x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = w.y_zero ? 0 : Math.min(...ys), y1 = Math.max(...ys);
  if (x1 === x0) { x0 -= 50; x1 += 50; }
  const pad = (y1 - y0) * 0.18 || 1;
  if (!w.y_zero) y0 -= pad;
  y1 += pad;
  const X = (v) => P.l + ((v - x0) / (x1 - x0)) * (CW - P.l - P.r);
  const Y = (v) => CH - P.b - ((v - y0) / (y1 - y0)) * (CH - P.t - P.b);
  const PALETTE = ["#8aa4b8", "#c1573f", "#3f7d5a", "#7d6b9e", "#c9a227"];
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = y0 + ((y1 - y0) * i) / 4, y = Y(v);
    g += `<line x1="${P.l}" y1="${y.toFixed(1)}" x2="${CW - P.r}" y2="${y.toFixed(1)}" stroke="var(--line)"/>` +
      `<text x="${P.l - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" class="ax">${v.toFixed(1)}</text>`;
  }
  for (const v of [...new Set(xs)].sort((a, b) => a - b)) {
    g += `<text x="${X(v).toFixed(1)}" y="${CH - 10}" text-anchor="middle" class="ax">${v}</text>`;
  }
  let body = "", legend = "";
  w.series.forEach((s, i) => {
    const col = s.color || PALETTE[i % PALETTE.length];
    const pts = (s.points || []).slice().sort((a, b) => a.x - b.x);
    if (pts.length > 1) {
      body += `<path d="${pts.map((p, j) => `${j ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join("")}" fill="none" stroke="${col}" stroke-width="2"/>`;
    }
    for (const p of pts) body += `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="3.5" fill="${col}"><title>${esc(s.name)} · ${p.x}: ${p.y}</title></circle>`;
    legend += `<g transform="translate(${CW - P.r + 8},${P.t + 14 + i * 18})"><rect width="10" height="10" y="-8" rx="2" fill="${col}"/>` +
      `<text x="15" y="0" class="ax">${esc(s.name)}</text></g>`;
  });
  const yl = w.y_label ? `<text transform="rotate(-90)" x="${-CH / 2}" y="12" text-anchor="middle" class="ax">${esc(w.y_label)}</text>` : "";
  return `<div class="chart-wrap"><svg viewBox="0 0 ${CW} ${CH}" width="100%" class="xyline">${g}${body}${legend}${yl}</svg></div>`;
}

// ------------------------------------------------------------- engine insights (Stats)

function initInsights(host) {
  let n = 0;
  const bar = document.createElement("div"); bar.className = "chart-toolbar";
  const body = document.createElement("div");
  [["All games", 0], ["Last 50", 50], ["Last 20", 20]].forEach(([lbl, val]) => {
    const b = document.createElement("button");
    b.className = "gbtn" + (val === n ? " on" : "");
    b.textContent = lbl;
    b.onclick = () => { n = val; [...bar.children].forEach((c) => c.classList.toggle("on", c === b)); load(); };
    bar.appendChild(b);
  });
  host.append(bar, body);
  async function load() {
    body.innerHTML = spinner("Reading the engine analyses of your games…");
    try {
      const d = await getJSON(`/api/insights?${who({ n })}`);
      const ctx = { after: [] };
      body.innerHTML = d.sections.map((s) => `<h3>${esc(s.title)}</h3>` + s.widgets.map((w) => renderWidget(w, ctx)).join("")).join("");
      ctx.after.forEach((f) => f());
    } catch (e) { body.innerHTML = errorBox(e.message); }
  }
  load();
}
