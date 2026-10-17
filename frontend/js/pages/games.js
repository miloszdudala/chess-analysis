// Games: the whole history, filterable, each row opening its review.

import { esc, getJSON, replaceHash, resultCls, resultMark, spinner, state, who } from "../api.js";

let cache = { key: null, rows: [] };

export async function gameList() {
  const key = `${state.user}|${state.format}`;
  if (cache.key !== key) {
    cache = { key, rows: await getJSON(`/api/games?${who()}`) };
  }
  return cache.rows;
}
export function forgetGames() { cache.key = null; }

export async function render(view, route) {
  view.innerHTML = spinner("Loading your games…");
  forgetGames();
  const rows = await gameList();
  const q = route.query;
  const f = { result: q.get("result") || "", color: q.get("color") || "", opening: q.get("opening") || "",
              reason: q.get("reason") || "", text: q.get("q") || "" };
  let shown = 60;
  const openings = [...new Set(rows.map((r) => r.opening).filter(Boolean))].sort();
  const reasons = [...new Map(rows.filter((r) => r.reason_label).map((r) => [r.reason_label, r.reason_label])).keys()].sort();
  const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`;

  view.innerHTML = `<div class="page-head"><div class="grow"><h1>Games</h1>` +
    `<p class="sub-title">Every ${esc(state.format || "")} game, newest first. Accuracy is the engine's ` +
    `(Lichess method); the reason is the review's one-line diagnosis.</p></div></div>` +
    `<div class="gl-filters">` +
    `<select data-f="result">${opt("", "All results", f.result)}${opt("win", "Wins", f.result)}${opt("draw", "Draws", f.result)}${opt("loss", "Losses", f.result)}</select>` +
    `<select data-f="color">${opt("", "Both colours", f.color)}${opt("white", "As White", f.color)}${opt("black", "As Black", f.color)}</select>` +
    `<select data-f="opening">${opt("", "Any opening", f.opening)}${openings.map((o) => opt(o, o, f.opening)).join("")}</select>` +
    `<select data-f="reason">${opt("", "Any reason", f.reason)}${reasons.map((o) => opt(o, o, f.reason)).join("")}</select>` +
    `<input data-f="text" placeholder="opponent…" value="${esc(f.text)}">` +
    `<span class="gl-sum" id="gl-sum"></span></div><div id="gl-table"></div>`;

  function filtered() {
    const t = f.text.toLowerCase();
    return rows.filter((r) => (!f.result || r.outcome === f.result) && (!f.color || r.color === f.color) &&
      (!f.opening || r.opening === f.opening) && (!f.reason || r.reason_label === f.reason) &&
      (!t || r.opponent.toLowerCase().includes(t)));
  }

  function draw() {
    const list = filtered();
    const w = list.filter((r) => r.outcome === "win").length, d = list.filter((r) => r.outcome === "draw").length;
    view.querySelector("#gl-sum").textContent = `${list.length} games · ${w}-${d}-${list.length - w - d}`;
    const body = list.slice(0, shown).map((r) => {
      const acc = r.accuracy != null ? `${Math.round(r.accuracy)}` : "—";
      const oacc = r.opp_accuracy != null ? `<span class="mut"> / ${Math.round(r.opp_accuracy)}</span>` : "";
      const flag = r.flag ? `<span title="${esc(r.note || "not counted")}">⚑ </span>` : "";
      return `<tr class="${r.flag ? "flagged" : ""}" data-id="${esc(r.id)}">` +
        `<td class="${resultCls(r.outcome)}">${flag}${resultMark(r.outcome)}</td>` +
        `<td class="l mono">${esc(r.date)}</td>` +
        `<td><span class="dot ${r.color}"></span></td>` +
        `<td class="l">${esc(r.opponent)} <span class="mut">${r.opp_elo || ""}</span></td>` +
        `<td class="l" title="${esc(r.line || "")}">${esc(r.opening || "—")}</td>` +
        `<td>${r.moves}</td><td class="acc">${acc}${oacc}</td>` +
        `<td class="l">${esc(r.reason_label || "")}</td>` +
        `<td>${r.positions ? `<span class="pill" title="positions to train">${r.positions}</span>` : ""}</td></tr>`;
    }).join("");
    view.querySelector("#gl-table").innerHTML = list.length
      ? `<div class="tablewrap"><table class="gl"><thead><tr><th></th><th class="l">Date</th><th></th>` +
        `<th class="l">Opponent</th><th class="l">Opening</th><th>Moves</th><th>Accuracy</th>` +
        `<th class="l">Why it ended so</th><th>Train</th></tr></thead><tbody>${body}</tbody></table></div>` +
        (list.length > shown ? `<div class="gl-more"><button class="btn" id="gl-more">Show ${Math.min(60, list.length - shown)} more</button></div>` : "")
      : `<div class="empty">No games match.</div>`;
    view.querySelectorAll("table.gl tbody tr").forEach((tr) => { tr.onclick = () => { location.hash = `#/game/${tr.dataset.id}`; }; });
    const more = view.querySelector("#gl-more");
    if (more) more.onclick = () => { shown += 60; draw(); };
  }

  view.querySelectorAll("[data-f]").forEach((el) => {
    const update = () => {
      f[el.dataset.f] = el.value;
      shown = 60;
      const p = new URLSearchParams();
      for (const [k, v] of Object.entries(f)) if (v) p.set(k === "text" ? "q" : k, v);
      replaceHash(`#/games${p.toString() ? "?" + p : ""}`);
      draw();
    };
    el.oninput = update;
  });
  draw();
}
