// Openings: an explorer over your games, players at your rating, and the
// elite book — on a board you can play moves on.

import { esc, evalText, getJSON, replaceHash, spinner, who } from "../api.js";
import { Board } from "../board.js";

export async function render(view, route) {
  const q = route.query;
  mountExplorer(view, {
    db: null,
    color: q.get("color") === "black" ? "black" : "white",
    moves: (q.get("moves") || "").split(",").filter(Boolean),
    hashFor: (color, moves) => `#/openings?color=${color}${moves.length ? "&moves=" + moves.join(",") : ""}`,
    title: "Openings",
  });
}

const pctTxt = (x) => (x == null ? "—" : `${Math.round(100 * x)}%`);

function scoreBar(w, d, l) {
  const t = w + d + l;
  if (!t) return "";
  const p = (x) => (100 * x) / t;
  return `<span class="sbar"><span style="width:${p(w)}%;background:var(--win)"></span>` +
    `<span style="width:${p(d)}%;background:var(--draw)"></span><span style="width:${p(l)}%;background:var(--loss)"></span></span>`;
}

// The explorer itself; Scout mounts it on an opponent's games (`db`).
export function mountExplorer(view, opts) {
  let color = opts.color, moves = opts.moves.slice(), pos = null, seq = 0, engineArrow = null;
  const who_ = opts.db ? esc(opts.db) : "You";
  view.innerHTML =
    `<div class="page-head"><div class="grow"><h1>${esc(opts.title)}</h1>` +
    `<p class="sub-title">${opts.db ? `${esc(opts.db)}'s games` : "Your games"}, players rated near ` +
    `${opts.db ? "them" : "you"} (the corpus), and 280,000 games between 2500+ and 2300+ players. ` +
    `Transpositions meet: a position is one node however it was reached.</p></div>` +
    `<div class="seg" id="ex-color"><button data-c="white">As White</button><button data-c="black">As Black</button></div></div>` +
    `<div class="ex"><div class="ex-left"><div class="ex-crumbs" id="ex-crumbs"></div><div id="ex-board"></div>` +
    `<div class="rv-nav"><button id="ex-start" title="Start">⏮</button><button id="ex-back" title="Back (←)">◀</button>` +
    `<button id="ex-flip" title="Flip">⇅</button></div><div class="ex-engine" id="ex-engine"></div></div>` +
    `<div><div class="ex-name" id="ex-name"></div><div class="ex-turn" id="ex-turn"></div>` +
    `<div id="ex-table" style="margin-top:.6rem"></div><div class="ex-games" id="ex-games"></div></div></div>` +
    `<h2>${opts.db ? "Their" : "Your"} openings by name</h2><div id="ex-rep"></div>`;
  const $q = (s) => view.querySelector(s);
  const board = new Board($q("#ex-board"), { orientation: color, onMove: (uci) => go([...moves, uci], true) });

  function setColor(c) {
    color = c;
    board.setOrientation(c);
    view.querySelectorAll("#ex-color button").forEach((b) => b.classList.toggle("on", b.dataset.c === c));
    loadRepertoire();
  }
  view.querySelectorAll("#ex-color button").forEach((b) => { b.onclick = () => { setColor(b.dataset.c); go(moves); }; });
  $q("#ex-start").onclick = () => go([]);
  $q("#ex-back").onclick = () => go(moves.slice(0, -1));
  $q("#ex-flip").onclick = () => board.flip();

  async function go(next, fromBoard = false) {
    const mine = ++seq;
    const params = { color, moves: next.join(",") };
    if (opts.db) params.db = opts.db;
    let d;
    try { d = await getJSON(`/api/explorer?${who(params)}`); }
    catch (e) { $q("#ex-table").innerHTML = `<p class="text" style="color:var(--loss)">${esc(e.message)}</p>`; return; }
    if (mine !== seq) return;
    if (d.moves.length < next.length) {            // the server stopped at an illegal move
      if (fromBoard) board.flash(next[next.length - 1].slice(2, 4));
      return;
    }
    const animate = next.length === moves.length + 1;
    moves = d.moves;
    pos = d;
    engineArrow = null;
    replaceHash(opts.hashFor(color, moves));
    draw(animate);
    engine(d.fen, mine);
  }

  function rowsFor(d) {
    const map = new Map();
    const add = (src, m) => {
      const r = map.get(m.uci) || { uci: m.uci, san: m.san };
      r[src] = m;
      map.set(m.uci, r);
    };
    d.me.moves.forEach((m) => add("me", m));
    (d.band ? d.band.moves : []).slice(0, 8).forEach((m) => add("band", m));
    d.masters.moves.slice(0, 6).forEach((m) => add("masters", m));
    return [...map.values()].sort((a, b) =>
      ((b.me && b.me.n) || 0) - ((a.me && a.me.n) || 0) ||
      ((b.band && b.band.n) || 0) - ((a.band && a.band.n) || 0) ||
      ((b.masters && b.masters.n) || 0) - ((a.masters && a.masters.n) || 0));
  }

  function paintBoard(animate) {
    const d = pos, total = d.me.games || 0;
    // the moves played here as blue arrows, thicker the more often chosen;
    // the engine's choice in green once it has answered
    const arrows = (d.me.moves || []).slice(0, 4).map((m) => ({
      uci: m.uci, color: "#3b78c4", width: 0.6 + 1.6 * (m.n / Math.max(1, total)), opacity: 0.55,
    }));
    if (engineArrow) arrows.push(engineArrow);
    board.set(d.fen, { last: moves.length ? moves[moves.length - 1] : null, arrows, animate });
  }

  function draw(animate) {
    const d = pos;
    const rows = rowsFor(d);
    const myTotal = d.me.games || 0;
    paintBoard(animate);
    // breadcrumbs
    let crumbs = `<a data-i="0" class="${moves.length ? "" : "cur"}">start</a>`;
    d.sans.forEach((s, i) => {
      const no = i % 2 === 0 ? `<span class="n">${i / 2 + 1}.</span>` : "";
      crumbs += `${no}<a data-i="${i + 1}" class="${i + 1 === moves.length ? "cur" : ""}">${esc(s)}</a>`;
    });
    $q("#ex-crumbs").innerHTML = crumbs;
    $q("#ex-crumbs").querySelectorAll("a").forEach((a) => { a.onclick = () => go(moves.slice(0, +a.dataset.i)); });
    $q("#ex-name").innerHTML = d.opening.name
      ? `<span class="eco">${esc(d.opening.eco)}</span>${esc(d.opening.name)}` : (moves.length ? "Unnamed line" : "Starting position");
    const yourMove = d.your_move;
    $q("#ex-turn").textContent = `${d.turn === "white" ? "White" : "Black"} to move — ` +
      (yourMove ? `${opts.db ? "their" : "your"} choice` : `${opts.db ? "their opponent's" : "your opponent's"} choice`) +
      ` · ${myTotal} of ${opts.db ? "their" : "your"} games reached this position` +
      (d.band ? ` · ${d.band.games} band games` : "");
    const bandTotal = d.band ? d.band.moves.reduce((s, m) => s + m.n, 0) : 0;
    const body = rows.map((r) => {
      const me = r.me, band = r.band, ms = r.masters;
      const costly = yourMove && me && me.loss != null && me.loss >= 5 && me.n >= 2;
      const bandScore = band ? (yourMove ? band.score : 1 - band.score) : null;
      return `<tr data-uci="${esc(r.uci)}" class="${costly ? "costly" : ""}">` +
        `<td class="mv">${esc(r.san)}${ms ? `<span class="book" title="played in ${Math.round(100 * ms.share)}% of elite games here">book</span>` : ""}</td>` +
        `<td class="n">${me ? me.n : `<span class="z">0</span>`}</td>` +
        `<td>${me ? `${pctTxt(me.score)}${scoreBar(me.w, me.d, me.l)}` : ""}</td>` +
        `<td class="loss">${yourMove && me && me.loss != null ? `−${me.loss.toFixed(1)}%` : ""}</td>` +
        `<td>${me && me.eval != null ? evalText(me.eval) : ""}</td>` +
        `<td class="n">${band ? `${Math.round(100 * band.n / Math.max(1, bandTotal))}%` : `<span class="z">—</span>`}</td>` +
        `<td>${bandScore != null ? pctTxt(bandScore) : ""}</td>` +
        `<td class="n">${ms ? `${Math.round(100 * ms.share)}%` : `<span class="z">—</span>`}</td></tr>`;
    }).join("");
    $q("#ex-table").innerHTML = rows.length
      ? `<div class="tablewrap"><table class="ex-moves"><thead><tr><th class="l">Move</th><th>${who_}</th>` +
        `<th>${opts.db ? "Their" : "Your"} score</th><th title="average win chance this move gave away (your moves only)">Cost</th>` +
        `<th title="engine eval after the move, averaged over the analysed games (White's view)">Eval</th>` +
        `<th>Band</th><th title="score of the side whose move it is, from ${opts.db ? "their" : "your"} side">Band score</th>` +
        `<th>Masters</th></tr></thead><tbody>${body}</tbody></table></div>` +
        `<p class="chart-hint" style="text-align:left">Highlighted: a move ${opts.db ? "they make" : "you make"} more than once that ` +
        `costs 5% or more of the win chance on average. Click a row or play on the board.</p>`
      : `<div class="empty">Nobody in any of the three sources reached this position.</div>`;
    $q("#ex-table").querySelectorAll("tbody tr").forEach((tr) => { tr.onclick = () => go([...moves, tr.dataset.uci], false); });
    const games = d.games || [];
    $q("#ex-games").innerHTML = games.length
      ? `<h3>${opts.db ? "Their" : "Your"} most recent games through here</h3><table class="recent-tbl reason-games"><tbody>` +
        games.map((g) => `<tr class="rrow"${opts.db ? "" : ` data-game-id="${esc(g.id)}" data-ply="${g.ply}"`}>` +
          `<td class="${g.outcome === "win" ? "res-win" : g.outcome === "loss" ? "res-loss" : "res-draw"}">${g.outcome === "win" ? "✓" : g.outcome === "loss" ? "✗" : "="}</td>` +
          `<td>${esc(g.date)}</td><td>${esc(g.opponent)} (${g.opp_elo || "?"})</td></tr>`).join("") + `</tbody></table>`
      : "";
  }

  async function engine(fen, mine) {
    const box = $q("#ex-engine");
    box.innerHTML = `<span class="spinner"></span>engine thinking…`;
    try {
      const d = await getJSON(`/api/analyse?fen=${encodeURIComponent(fen)}&depth=16&multipv=3&pv=6`);
      if (mine !== seq) return;
      if (!d.best || !d.best.length) { box.innerHTML = `<span class="mut">Game over.</span>`; return; }
      box.innerHTML = `<div class="rv-eh">Engine · depth ${d.depth}</div>` + d.best.map((m, i) =>
        `<div class="rv-line" data-uci="${esc(m.uci)}"><i style="background:${i ? "#7cc89c" : "#2f8f4e"}"></i>` +
        `<b>${esc(evalText(m.cp))}</b><span class="pv">${esc((m.pv || [m.san]).join(" "))}</span></div>`).join("");
      box.querySelectorAll(".rv-line").forEach((el) => { el.onclick = () => go([...moves, el.dataset.uci], false); });
      engineArrow = { uci: d.best[0].uci, color: "#2f8f4e", width: 1.4, opacity: 0.85 };
      paintBoard(false);
    } catch (e) { box.innerHTML = `<span class="mut">Engine unavailable.</span>`; }
  }

  async function loadRepertoire() {
    const host = $q("#ex-rep");
    host.innerHTML = spinner("Naming the openings…");
    try {
      const params = { color };
      if (opts.db) params.db = opts.db;
      const rows = await getJSON(`/api/repertoire?${who(params)}`);
      host.innerHTML = rows.length
        ? `<div class="tablewrap"><table><thead><tr><th>Opening</th><th>Games</th><th>Score</th>` +
          `<th title="average own moves inside the elite book">Book moves</th>` +
          `<th title="share of games where this side left the book first">Left book first</th><th>Usual line</th></tr></thead><tbody>` +
          rows.map((r) => `<tr><td>${esc(r.name)}</td><td>${r.games}</td><td>${pctTxt(r.score)}</td>` +
            `<td>${r.book.toFixed(1)}</td><td>${pctTxt(r.left_first)}</td><td>${esc(r.line)}</td></tr>`).join("") +
          `</tbody></table></div><p class="chart-hint" style="text-align:left">Scores here describe; ` +
          `they don't rank openings — a handful of games per line is mostly luck.</p>`
        : `<p class="text">Not enough games as ${color} yet.</p>`;
    } catch (e) { host.innerHTML = ""; }
  }

  // keyboard: ← steps back
  if (window._exKey) window.removeEventListener("keydown", window._exKey);
  window._exKey = (e) => {
    if (!document.body.contains(view) || !view.querySelector("#ex-board")) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "ArrowLeft") { go(moves.slice(0, -1)); e.preventDefault(); }
  };
  window.addEventListener("keydown", window._exKey);

  setColor(color);
  go(moves);
}
