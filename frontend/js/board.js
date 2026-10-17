// A chessboard: renders a FEN, takes moves by click or drag.
//
// The board never decides what is legal — the server does (python-chess),
// so there is one source of truth. A move is reported through `onMove(uci)`;
// the owner asks the server and calls `set()` with whatever happens next.

import { PIECES } from "./pieces.js";

const NS = "http://www.w3.org/2000/svg";
const S = 10;                      // one square, in viewBox units
const FILES = "abcdefgh";

export function parseFen(fen) {
  const board = {};                // "e4" -> "P"
  const [rows, turn] = fen.split(" ");
  rows.split("/").forEach((row, r) => {
    let f = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) f += +ch;
      else board[FILES[f++] + (8 - r)] = ch;
    }
  });
  return { board, turn: turn === "b" ? "black" : "white" };
}

const isWhite = (p) => p === p.toUpperCase();

export class Board {
  constructor(host, opts = {}) {
    this.host = host;
    this.orientation = opts.orientation || "white";
    this.onMove = opts.onMove || null;
    this.coords = opts.coords !== false;
    this.fen = null;
    this.opts = {};
    this.selected = null;
    this.drag = null;
    this.el = document.createElement("div");
    this.el.className = "bd" + (this.onMove ? "" : " static");
    host.appendChild(this.el);
    this._bind();
  }

  set(fen, opts = {}) {
    const prev = this.fen;
    this.fen = fen;
    this.opts = opts;
    this.selected = null;
    this._render();
    if (opts.animate && prev && opts.last) this._slide(opts.last);
  }

  setOrientation(o) { this.orientation = o; if (this.fen) this._render(); }
  flip() { this.setOrientation(this.orientation === "white" ? "black" : "white"); }

  flash(square, cls = "sq-bad") {
    const [x, y] = this._xy(square);
    const r = document.createElementNS(NS, "rect");
    Object.entries({ x, y, width: S, height: S, class: `${cls} flash-bad` })
      .forEach(([k, v]) => r.setAttribute(k, v));
    this.svg.querySelector(".marks").appendChild(r);
    setTimeout(() => r.remove(), 600);
  }

  // --- geometry -------------------------------------------------------------------
  _xy(sq) {
    const f = FILES.indexOf(sq[0]), r = +sq[1] - 1;
    const col = this.orientation === "white" ? f : 7 - f;
    const row = this.orientation === "white" ? 7 - r : r;
    return [col * S, row * S];
  }
  _center(sq) { const [x, y] = this._xy(sq); return [x + S / 2, y + S / 2]; }
  _squareAt(clientX, clientY) {
    const r = this.svg.getBoundingClientRect();
    const col = Math.floor(((clientX - r.left) / r.width) * 8);
    const row = Math.floor(((clientY - r.top) / r.height) * 8);
    if (col < 0 || col > 7 || row < 0 || row > 7) return null;
    const f = this.orientation === "white" ? col : 7 - col;
    const rank = this.orientation === "white" ? 7 - row : row;
    return FILES[f] + (rank + 1);
  }

  // --- drawing ----------------------------------------------------------------------
  _render() {
    const { board } = parseFen(this.fen);
    const o = this.opts;
    let sq = "", marks = "", co = "", pcs = "";
    for (let f = 0; f < 8; f++) for (let r = 0; r < 8; r++) {
      const name = FILES[f] + (r + 1);
      const [x, y] = this._xy(name);
      const light = (f + r) % 2 === 1;
      sq += `<rect x="${x}" y="${y}" width="${S}" height="${S}" class="${light ? "sq-l" : "sq-d"}"/>`;
    }
    if (o.last) {
      for (const s of [o.last.slice(0, 2), o.last.slice(2, 4)]) {
        const [x, y] = this._xy(s);
        marks += `<rect x="${x}" y="${y}" width="${S}" height="${S}" class="sq-last${o.quality ? " q-" + o.quality : ""}"/>`;
      }
    }
    for (const m of o.marks || []) {
      const [x, y] = this._xy(m.sq);
      marks += `<rect x="${x}" y="${y}" width="${S}" height="${S}" class="${m.cls}"/>`;
    }
    if (this.coords) {
      for (let i = 0; i < 8; i++) {
        const file = this.orientation === "white" ? FILES[i] : FILES[7 - i];
        const rank = this.orientation === "white" ? 8 - i : i + 1;
        const fileOnLight = (i + (this.orientation === "white" ? 0 : 1)) % 2 === 1;
        co += `<text x="${i * S + S - 0.6}" y="${8 * S - 0.7}" text-anchor="end" class="co ${fileOnLight ? "on-l" : "on-d"}">${file}</text>`;
        co += `<text x="0.5" y="${i * S + 2.7}" class="co ${i % 2 === 0 ? "on-l" : "on-d"}">${rank}</text>`;
      }
    }
    for (const [name, p] of Object.entries(board)) {
      const [x, y] = this._xy(name);
      // the outer group carries no transform attribute: a CSS transform (the
      // slide animation) would replace it rather than compose with it
      pcs += `<g class="pc" data-sq="${name}">` +
        `<g transform="translate(${x},${y}) scale(${S / 45})">${PIECES[p]}</g></g>`;
    }
    const arrows = (o.arrows || []).map((a) => this._arrow(a)).join("");
    this.el.innerHTML =
      `<svg viewBox="0 0 ${8 * S} ${8 * S}" xmlns="${NS}">` +
      `<g class="squares">${sq}</g><g class="marks">${marks}</g><g>${co}</g>` +
      `<g class="pieces">${pcs}</g><g class="sel"></g><g class="arrows" pointer-events="none">${arrows}</g></svg>`;
    this.svg = this.el.querySelector("svg");
  }

  _arrow({ uci, color = "#2f8f4e", width = 1.6, opacity = 0.8 }) {
    if (!uci || uci.length < 4) return "";
    const [x1, y1] = this._center(uci.slice(0, 2)), [x2, y2] = this._center(uci.slice(2, 4));
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len, head = Math.max(2.6, width * 1.9), hw = Math.max(1.5, width * 1.15);
    const ex = x2 - ux * head, ey = y2 - uy * head, px = -uy, py = ux;
    const sx = x1 + ux * 2.2, sy = y1 + uy * 2.2;
    return `<g opacity="${opacity}"><line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" stroke="${color}" ` +
      `stroke-width="${width}" stroke-linecap="round"/>` +
      `<polygon points="${x2},${y2} ${ex + px * hw},${ey + py * hw} ${ex - px * hw},${ey - py * hw}" fill="${color}"/></g>`;
  }

  _slide(uci) {
    const from = uci.slice(0, 2), to = uci.slice(2, 4);
    const g = this.svg.querySelector(`.pc[data-sq="${to}"]`);
    if (!g) return;
    const [fx, fy] = this._xy(from), [tx, ty] = this._xy(to);
    g.style.transition = "none";
    g.style.transform = `translate(${fx - tx}px, ${fy - ty}px)`;
    g.getBoundingClientRect();
    requestAnimationFrame(() => {
      g.style.transition = "transform .18s ease-out";
      g.style.transform = "translate(0px, 0px)";
    });
  }

  _showSelected() {
    const g = this.svg.querySelector(".sel");
    if (!g) return;
    if (!this.selected) { g.innerHTML = ""; return; }
    const [x, y] = this._xy(this.selected);
    g.innerHTML = `<rect x="${x}" y="${y}" width="${S}" height="${S}" class="sq-sel"/>`;
  }

  // --- input ------------------------------------------------------------------------
  _movable(sq) {
    const { board, turn } = parseFen(this.fen);
    const p = board[sq];
    return p && (isWhite(p) ? "white" : "black") === turn;
  }

  _commit(from, to) {
    this.selected = null;
    this._showSelected();
    if (from !== to && this.onMove) this.onMove(from + to);
  }

  _bind() {
    this.el.addEventListener("pointerdown", (e) => {
      if (!this.onMove || !this.fen || e.button > 0) return;
      const sq = this._squareAt(e.clientX, e.clientY);
      if (!sq) return;
      if (this.selected && sq !== this.selected && !this._movable(sq)) {
        this._commit(this.selected, sq);            // second click: the target
        return;
      }
      if (!this._movable(sq)) { this.selected = null; this._showSelected(); return; }
      this.drag = { from: sq, x: e.clientX, y: e.clientY, moved: false, wasSelected: this.selected === sq };
      this.selected = sq;
      this._showSelected();
      this.el.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    this.el.addEventListener("pointermove", (e) => {
      const d = this.drag;
      if (!d) return;
      if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) {
        d.moved = true;
        const g = this.svg.querySelector(`.pc[data-sq="${d.from}"]`);
        if (g) {
          g.classList.add("dragging");
          const size = this.svg.getBoundingClientRect().width / 8;
          d.ghost = document.createElement("div");
          d.ghost.className = "ghost";
          d.ghost.style.width = d.ghost.style.height = `${size}px`;
          const p = parseFen(this.fen).board[d.from];
          d.ghost.innerHTML = `<svg viewBox="0 0 45 45" width="100%" height="100%">${PIECES[p]}</svg>`;
          this.el.appendChild(d.ghost);
        }
      }
      if (d.ghost) { d.ghost.style.left = `${e.clientX}px`; d.ghost.style.top = `${e.clientY}px`; }
    });
    const end = (e) => {
      const d = this.drag;
      if (!d) return;
      this.drag = null;
      if (d.ghost) d.ghost.remove();
      const g = this.svg.querySelector(".pc.dragging");
      if (g) g.classList.remove("dragging");
      if (d.moved) {
        const to = this._squareAt(e.clientX, e.clientY);
        if (to && to !== d.from) this._commit(d.from, to);
        else { this.selected = null; this._showSelected(); }
      } else if (d.wasSelected) {
        this.selected = null;                          // tapping a piece again drops it
        this._showSelected();
      }
    };
    this.el.addEventListener("pointerup", end);
    this.el.addEventListener("pointercancel", end);
  }
}
