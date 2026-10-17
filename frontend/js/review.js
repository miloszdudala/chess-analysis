// The game review board: the game move by move, the engine's view of each
// position, and live exploration of any other line.

import { esc, evalText, fmtClock, getJSON, winProb } from "./api.js";
import { Board } from "./board.js";

const ARROW_BEST = "#2f8f4e";
const ARROW_ALT = "#7cc89c";
const SENSIBLE_CP = 90;          // alternatives shown only within this of the best
const QUAL = { best: "Best move", inaccuracy: "Inaccuracy", mistake: "Mistake", blunder: "Blunder" };
const SYM = { inaccuracy: "?!", mistake: "?", blunder: "??" };

const moveQual = (m) => (m.label === "ok" ? (m.best_san && m.san === m.best_san ? "best" : null) : m.label);

function sensible(fen, cands) {
  const c = (cands || []).slice(0, 3);
  if (!c.length) return [];
  const white = (fen.split(" ")[1] || "w") === "w";
  const top = c[0].cp;
  return c.filter((x, i) => i === 0 || (white ? top - x.cp : x.cp - top) <= SENSIBLE_CP);
}

export function buildReviewBoard(host, data) {
  const positions = data.positions, moves = data.moves;
  if (!positions || positions.length < 2) return;
  const div = data.division || {};
  const clocks = data.clocks || [];
  let idx = 0, variation = null;
  const stack = [];

  host.innerHTML =
    `<div class="rv">` +
      `<div class="rv-evalv"><div class="fill"></div><span class="num top"></span><span class="num bot"></span></div>` +
      `<div class="rv-main"><div class="rv-player top"></div><div class="rv-board"></div>` +
        `<div class="rv-player bottom"></div>` +
        `<div class="rv-tip">Move a piece to explore a line with the engine · ← → to step · F to flip</div></div>` +
      `<div class="rv-side"><div class="rv-info"></div><div class="rv-engine"></div>` +
        `<div class="rv-varbar" style="display:none"></div>` +
        `<div class="rv-nav"><button data-go="start" title="Start (Home)">⏮</button>` +
        `<button data-go="prev" title="Previous (←)">◀</button><button data-go="next" title="Next (→)">▶</button>` +
        `<button data-go="end" title="End (End)">⏭</button><button data-go="flip" title="Flip (F)">⇅</button></div>` +
        `<div class="rv-moves"></div></div>` +
    `</div>`;
  const q = (s) => host.querySelector(s);
  const board = new Board(q(".rv-board"), { orientation: data.orientation, onMove: explore });

  function view() {
    if (variation) return { fen: variation.fen, last: variation.uci, best: variation.best, cp: variation.cp, qual: null };
    const pos = positions[idx];
    return { fen: pos.fen, last: idx > 0 ? moves[idx - 1].uci : null, best: pos.best, cp: pos.cp,
             qual: idx > 0 ? moveQual(moves[idx - 1]) : null };
  }

  function clockAt(color) {
    // the clock after this colour's latest move at or before the shown position
    for (let p = idx; p >= 1; p--) {
      const mover = p % 2 === 1 ? "white" : "black";
      if (mover === color && clocks[p - 1] != null) return clocks[p - 1];
    }
    return null;
  }

  function players() {
    const flip = board.orientation === "black";
    const topColor = flip ? "white" : "black", botColor = flip ? "black" : "white";
    const line = (color) => {
      const c = clockAt(color);
      const low = c != null && c < 60;
      return `<span class="name">${color === "white" ? "○" : "●"} ${esc(color === "white" ? data.white : data.black)}</span>` +
        (c != null ? `<span class="clock${low ? " low" : ""}">${fmtClock(c)}</span>` : "");
    };
    q(".rv-player.top").innerHTML = line(topColor);
    q(".rv-player.bottom").innerHTML = line(botColor);
  }

  function phaseAt(ply) {
    // the phase of the position after `ply` plies
    if (div.end != null && ply >= div.end) return "Endgame";
    if (div.mid != null && ply >= div.mid) return "Middlegame";
    return "Opening";
  }

  function render(animate = false) {
    const v = view();
    const arrows = sensible(v.fen, v.best).map((m, i) =>
      ({ uci: m.uci, color: i ? ARROW_ALT : ARROW_BEST, width: i ? 0.9 : 1.6, opacity: i ? 0.75 : 0.85 })).reverse();
    board.set(v.fen, { last: v.last, quality: v.qual, arrows, animate });
    // eval bar: white from the bottom when white is at the bottom
    const w = winProb(v.cp);
    const flip = board.orientation === "black";
    q(".rv-evalv .fill").style.height = `${flip ? 100 - w : w}%`;
    q(".rv-evalv").style.background = flip ? "var(--ev-white)" : "var(--ev-black)";
    q(".rv-evalv .fill").style.background = flip ? "var(--ev-black)" : "var(--ev-white)";
    const txt = evalText(v.cp), whiteAhead = v.cp >= 0;
    const top = q(".rv-evalv .num.top"), bot = q(".rv-evalv .num.bot");
    top.textContent = whiteAhead === flip ? txt : "";
    bot.textContent = whiteAhead === flip ? "" : txt;
    top.style.color = flip ? "var(--ev-black)" : "var(--ev-white)";
    bot.style.color = flip ? "var(--ev-white)" : "var(--ev-black)";
    players();

    const info = q(".rv-info");
    if (variation) {
      info.innerHTML = `<span class="rv-mv">Variation</span> <span class="rv-tag rv-live">live engine</span>` +
        ` <span class="mut">${esc(stack.map((s) => s.san).join(" "))}</span>`;
    } else if (idx === 0) {
      info.innerHTML = `<span class="rv-mv">Starting position</span>`;
    } else {
      const m = moves[idx - 1], no = Math.ceil(idx / 2), dots = idx % 2 ? "." : "…";
      const qk = moveQual(m);
      const tag = qk ? ` <span class="rv-tag rv-${qk}">${QUAL[qk]}${m.label !== "ok" ? ` −${m.wp_loss}%` : ""}</span>` : "";
      const better = m.label !== "ok" && m.best_san && m.best_san !== m.san ? ` · best was <b class="mono">${esc(m.best_san)}</b>` : "";
      info.innerHTML = `<span class="rv-mv">${no}${dots} ${esc(m.san)}</span>${tag}` +
        `<span class="rv-tag rv-phase">${phaseAt(idx - 1)}</span>${better}`;
    }
    const shown = sensible(v.fen, v.best);
    q(".rv-engine").innerHTML = shown.length
      ? `<div class="rv-eh">Engine</div>` + shown.map((m, i) =>
          `<div class="rv-line" data-uci="${esc(m.uci)}"><i style="background:${i ? ARROW_ALT : ARROW_BEST}"></i>` +
          `<b>${esc(evalText(m.cp))}</b><span>${esc(m.san)}</span></div>`).join("")
      : `<div class="rv-eh">Engine</div><span class="mut">${variation ? "—" : "no candidates stored"}</span>`;
    q(".rv-engine").querySelectorAll(".rv-line").forEach((el) => { el.onclick = () => explore(el.dataset.uci); });

    const vb = q(".rv-varbar");
    if (variation) {
      vb.style.display = "";
      vb.innerHTML = `<button data-v="back">← undo move</button><button data-v="exit">⟲ back to game</button>`;
      vb.querySelector('[data-v="back"]').onclick = () => { stack.pop(); variation = stack[stack.length - 1] || null; render(); };
      vb.querySelector('[data-v="exit"]').onclick = () => { variation = null; stack.length = 0; render(); };
    } else { vb.style.display = "none"; vb.innerHTML = ""; }
    host.querySelectorAll(".rv-m").forEach((el) => el.classList.toggle("on", !variation && +el.dataset.ply === idx));
    const cur = host.querySelector(".rv-m.on");
    if (cur) cur.scrollIntoView({ block: "nearest" });
    window.dispatchEvent(new CustomEvent("rv-ply", { detail: variation ? -1 : idx }));
  }

  async function explore(uci) {
    const from = view().fen;
    try {
      const d = await getJSON(`/api/analyse?fen=${encodeURIComponent(from)}&move=${uci}&depth=14`);
      if (!d.legal) { board.flash(uci.slice(2, 4)); return; }
      stack.push({ fen: d.fen, cp: d.cp, best: d.best, uci, san: d.move_san });
      variation = stack[stack.length - 1];
      render(true);
    } catch (e) { board.flash(uci.slice(2, 4)); }
  }

  // move list, with a marker where each phase begins
  let rows = "";
  for (let i = 0; i < moves.length; i += 2) {
    for (const [pos, label] of [[div.mid, "Middlegame"], [div.end, "Endgame"]]) {
      if (pos != null && pos > 0 && (pos === i || pos === i + 1)) rows += `<div class="rv-ph">${label}</div>`;
    }
    const cell = (m, ply) => m
      ? `<span class="rv-m m-${m.label}" data-ply="${ply}">${esc(m.san)}<span class="sym">${SYM[m.label] || ""}</span></span>`
      : "<span></span>";
    rows += `<span class="rv-no">${i / 2 + 1}.</span>${cell(moves[i], i + 1)}${cell(moves[i + 1], i + 2)}`;
  }
  q(".rv-moves").innerHTML = rows;
  q(".rv-moves").onclick = (e) => {
    const el = e.target.closest(".rv-m"); if (!el) return;
    variation = null; stack.length = 0; idx = +el.dataset.ply; render();
  };

  function go(d) {
    if (d === "flip") { board.flip(); render(); return; }
    const before = idx;
    variation = null; stack.length = 0;
    if (d === "prev") idx = Math.max(0, idx - 1);
    else if (d === "next") idx = Math.min(moves.length, idx + 1);
    else if (d === "end") idx = moves.length;
    else if (d === "start") idx = 0;
    else idx = Math.max(0, Math.min(moves.length, +d));
    render(d === "next" && idx === before + 1);
  }
  host.querySelectorAll(".rv-nav button").forEach((b) => { b.onclick = () => go(b.dataset.go); });

  // jump requests from the eval graph, the key-moment chips and deep links
  if (window._rvGoto) window.removeEventListener("rv-goto", window._rvGoto);
  window._rvGoto = (e) => {
    if (!document.body.contains(host)) return;
    go(String(e.detail));
    host.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  window.addEventListener("rv-goto", window._rvGoto);
  if (window._rvKey) window.removeEventListener("keydown", window._rvKey);
  window._rvKey = (e) => {
    if (!document.body.contains(host)) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
    const map = { ArrowLeft: "prev", ArrowRight: "next", Home: "start", End: "end" };
    if (map[e.key]) { go(map[e.key]); e.preventDefault(); }
    else if (e.key === "f" || e.key === "F") go("flip");
  };
  window.addEventListener("keydown", window._rvKey);
  render();
}
