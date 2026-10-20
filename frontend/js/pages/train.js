// Train: positions from your own games, on a spaced-repetition schedule.

import { esc, evalText, getJSON, postJSON, replaceHash, spinner, state } from "../api.js";
import { Board } from "../board.js";

const KIND_LABEL = { mistake: "Your mistake", missed: "Missed chance", opening: "Opening fix" };
const u = () => encodeURIComponent(state.user);

export async function render(view, route) {
  const f = { kind: route.query.get("kind") || "", phase: route.query.get("phase") || "",
              theme: route.query.get("theme") || "", game: route.query.get("game") || "" };
  view.innerHTML = spinner("Collecting positions from your games…");
  let summary = await postJSON(`/api/train/sync?user=${u()}`);
  const session = { tried: 0, first: 0 };

  const rules = summary.rules || {};
  view.innerHTML =
    `<div class="page-head"><div class="grow"><h1>Train</h1><p class="sub-title">Positions from your own games: ` +
    `your moves that cost ${rules.min_loss ?? "?"}% win chance or more, and replies that gave back an opponent's ` +
    `gift of ${rules.gift ?? "?"}% or more. Solve each one; it comes back on a spaced-repetition schedule until it ` +
    `sticks. Any move within ${rules.tolerance ?? "?"}% win chance of the engine's best counts as solved. ` +
    `<a class="guide-link" href="#/guide?s=win-chance">What win chance means →</a></p></div></div>` +
    `<div class="tr"><div><div id="tr-board"></div></div><div class="tr-panel">` +
    `<div class="chips" id="tr-kind"></div><div class="chips" id="tr-phase"></div>` +
    `<div class="tr-stats" id="tr-stats"></div>` +
    `<div class="tr-card" id="tr-card"></div><div class="tr-feedback" id="tr-fb"></div>` +
    `<div class="tr-buttons" id="tr-btns"></div>` +
    `<div class="tr-keys"><span><span class="kbd">H</span> hint</span><span><span class="kbd">S</span> solution</span>` +
    `<span><span class="kbd">N</span> next</span></div></div></div>`;
  const $q = (s) => view.querySelector(s);
  let p = null, done = false, attempts = 0, hinted = false, reveal = null;
  const board = new Board($q("#tr-board"), { onMove: attempt });

  function chips() {
    const k = [["", "All"], ["mistake", "Mistakes"], ["missed", "Missed chances"], ["opening", "Opening fixes"]];
    const ph = [["", "Any phase"], ["Opening", "Opening"], ["Middlegame", "Middlegame"], ["Endgame", "Endgame"]];
    const by = summary.by_kind || {};
    $q("#tr-kind").innerHTML = `<span class="lead">Kind</span>` + k.map(([v, l]) =>
      `<button class="chip${f.kind === v ? " on" : ""}" data-k="${v}">${l}${v && by[v] ? ` · ${by[v].total}` : ""}</button>`).join("");
    $q("#tr-phase").innerHTML = `<span class="lead">Phase</span>` + ph.map(([v, l]) =>
      `<button class="chip${f.phase === v ? " on" : ""}" data-p="${v}">${l}</button>`).join("") +
      (f.theme ? `<button class="chip on" data-t="">${esc(f.theme)} ✕</button>` : "") +
      (f.game ? `<button class="chip on" data-g="">this game only ✕</button>` : "");
    view.querySelectorAll("[data-k]").forEach((b) => { b.onclick = () => { f.kind = b.dataset.k; refilter(); }; });
    view.querySelectorAll("[data-p]").forEach((b) => { b.onclick = () => { f.phase = b.dataset.p; refilter(); }; });
    view.querySelectorAll("[data-t]").forEach((b) => { b.onclick = () => { f.theme = ""; refilter(); }; });
    view.querySelectorAll("[data-g]").forEach((b) => { b.onclick = () => { f.game = ""; refilter(); }; });
  }
  function refilter() {
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
    replaceHash(`#/train${qs ? "?" + qs : ""}`);
    chips();
    next();
  }
  function stats() {
    const s = summary;
    $q("#tr-stats").innerHTML =
      `<div class="tr-stat"><b>${s.due}</b><span>due now</span></div>` +
      `<div class="tr-stat"><b>${Math.min(s.new, s.new_left_today)}</b><span>new today</span></div>` +
      `<div class="tr-stat"><b>${s.learned}/${s.total}</b><span>learned</span></div>` +
      `<div class="tr-stat"><b>${session.tried ? `${session.first}/${session.tried}` : s.streak ? `${s.streak}d` : "—"}</b>` +
      `<span>${session.tried ? "first try" : "streak"}</span></div>`;
  }

  function prompt(pz) {
    const g = pz.game, when = `${esc(g.date)} vs ${esc(g.opponent)}${g.opp_elo ? ` (${g.opp_elo})` : ""}, move ${g.move_no}`;
    const side = pz.turn === "white" ? "White" : "Black";
    if (pz.kind === "missed") {
      return [`${side} to move — your opponent just slipped.`,
        `${when}. ${esc(pz.prev_san || "Their last move")} handed you ${pz.gift}% of win chance, and in the ` +
        `game ${esc(pz.played_san)} gave ${pz.played_loss}% of it back. Take it.`];
    }
    if (pz.kind === "opening") {
      return [`${side} to move — fix the habit.`,
        `You reached this position ${pz.times} times and played ${esc(pz.played_san)} each time ` +
        `(−${pz.played_loss}% on average). What should you play instead? Last seen ${when}.`];
    }
    return [`${side} to move — find a better move.`,
      `${when}. In the game you played ${esc(pz.played_san)} here, giving away ${pz.played_loss}% of win chance.`];
  }

  async function next(skip = false) {
    const params = new URLSearchParams({ user: state.user });
    for (const [k, v] of Object.entries(f)) if (v) params.set(k, v);
    if (skip && p) params.set("exclude", p.id);
    const d = await getJSON(`/api/train/next?${params}`);
    summary = d.summary;
    stats();
    chips();
    p = d.puzzle; done = false; attempts = 0; hinted = false; reveal = null;
    $q("#tr-fb").className = "tr-feedback";
    if (!p) {
      $q("#tr-card").innerHTML = `<div class="tr-prompt">Nothing left here for now.</div><div class="tr-ctx">` +
        (summary.total ? `Every position in this set is scheduled for later. Widen the filters, or come back tomorrow.`
                       : `No positions yet — they come from games analysed at review depth, which runs in the background.`) +
        `</div>`;
      $q("#tr-btns").innerHTML = (f.kind || f.phase || f.theme || f.game)
        ? `<button class="btn" id="tr-all">Show every kind and phase</button>` : "";
      const all = $q("#tr-all");
      if (all) all.onclick = () => { f.kind = f.phase = f.theme = f.game = ""; refilter(); };
      board.set("8/8/8/8/8/8/8/8 w - - 0 1");
      return;
    }
    const [head, ctx] = prompt(p);
    const status = p.status === "review" ? `review · seen ${p.reps + p.lapses}×` : p.status === "ahead" ? "early review" : p.status === "game" ? "from this game" : "new";
    $q("#tr-card").innerHTML = `<div class="tr-kind">${KIND_LABEL[p.kind]} · ${status}</div>` +
      `<div class="tr-prompt">${head}</div><div class="tr-ctx">${ctx}</div>` +
      `<div class="tr-themes">${p.themes.map((t) => `<span class="tr-theme">${esc(t)}</span>`).join("")}</div>`;
    buttons();
    board.setOrientation(p.turn);
    if (p.prev_fen && p.prev_uci) {
      board.set(p.prev_fen, {});
      setTimeout(() => { if (p) board.set(p.fen, { last: p.prev_uci, animate: true }); }, 450);
    } else {
      board.set(p.fen, {});
    }
  }

  function buttons() {
    $q("#tr-btns").innerHTML = done
      ? `<button class="btn primary" id="tr-next">Next position →</button>` +
        `<a class="btn" href="#/game/${esc(p.gid)}?ply=${p.ply - 1}">Open the game here</a>`
      : `<button class="btn" id="tr-hint">Hint</button><button class="btn" id="tr-sol">Show solution</button>` +
        `<button class="btn ghost" id="tr-skip">Skip</button>`;
    const on = (id, fn) => { const b = $q(id); if (b) b.onclick = fn; };
    on("#tr-next", () => next());
    on("#tr-hint", hint);
    on("#tr-sol", solution);
    on("#tr-skip", () => next(true));
  }

  async function getReveal() {
    if (!reveal) reveal = await getJSON(`/api/train/reveal?user=${u()}&id=${encodeURIComponent(p.id)}`);
    return reveal;
  }

  async function hint() {
    if (!p || done) return;
    hinted = true;
    const r = await getReveal();
    const from = r.best[0].uci.slice(0, 2);
    board.set(p.fen, { last: p.prev_uci, marks: [{ sq: from, cls: "sq-hint" }] });
    feedback("info", "Hint", `Move the highlighted piece.`);
  }

  function feedback(kind, head, body, line = "") {
    const fb = $q("#tr-fb");
    fb.className = `tr-feedback on ${kind}`;
    fb.innerHTML = `<div class="h">${head}</div><div>${body}</div>${line ? `<div class="line">${line}</div>` : ""}`;
  }

  async function finish(grade) {
    done = true;
    session.tried += 1;
    if (grade === "good") session.first += 1;
    try { await postJSON(`/api/train/grade?user=${u()}&id=${encodeURIComponent(p.id)}&grade=${grade}`); } catch (e) { /* shown below */ }
    window.dispatchEvent(new CustomEvent("train-changed"));
    stats();
    buttons();
  }

  function answerText(r) {
    const best = r.best.map((b) => `<b class="mono">${esc(b.san)}</b> (${evalText(b.cp)})`).join(", ");
    return `Best: ${best}. In the game: <b class="mono">${esc(r.played.san)}</b> (${evalText(r.played.cp_after)}).`;
  }

  async function attempt(uci) {
    if (!p || done) return;
    let res;
    try { res = await postJSON(`/api/train/attempt?user=${u()}&id=${encodeURIComponent(p.id)}&uci=${uci}`); }
    catch (e) { feedback("bad", "Couldn't check that move", esc(e.message)); return; }
    if (!res.legal) { board.flash(uci.slice(2, 4)); return; }
    if (res.solved) {
      board.set(res.fen_after, { last: res.uci, quality: "best", animate: true });
      const r = await getReveal();
      const exact = r.best.some((b) => b.uci === res.uci);
      feedback("ok", `✓ ${esc(res.san)} — ${exact ? (r.best[0].uci === res.uci ? "the engine's choice" : "one of the engine's choices") : "as good as the best"}`,
        answerText(r), r.line.length ? `Engine line: ${esc(r.line.join(" "))}` : "");
      await finish(attempts === 0 && !hinted ? "good" : "hard");
    } else {
      attempts += 1;
      board.flash(uci.slice(2, 4));
      feedback("bad", `✗ ${esc(res.san)} gives away ${res.loss}% win chance compared with the best move`,
        attempts >= 3 ? "Still not it — try once more, or show the solution." : "Try again.");
    }
  }

  async function solution() {
    if (!p || done) return;
    const r = await getReveal();
    try {
      const d = await getJSON(`/api/analyse?fen=${encodeURIComponent(p.fen)}&move=${r.best[0].uci}&depth=8&multipv=1`);
      board.set(d.fen, { last: r.best[0].uci, quality: "best", animate: true });
    } catch (e) { /* the text still says it */ }
    feedback("info", "The answer", answerText(r), r.line.length ? `Engine line: ${esc(r.line.join(" "))}` : "");
    await finish("fail");
  }

  if (window._trKey) window.removeEventListener("keydown", window._trKey);
  window._trKey = (e) => {
    if (!document.body.contains(view) || !view.querySelector("#tr-board")) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "n" || (e.key === "Enter" && done)) next(!done);
    else if (e.key === "h") hint();
    else if (e.key === "s") solution();
  };
  window.addEventListener("keydown", window._trKey);
  chips();
  stats();
  next();
}
