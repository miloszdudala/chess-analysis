// One game's review: the verdict, the board, the numbers, the key moments.

import { esc, getJSON, spinner, state } from "../api.js";
import { renderDoc } from "../widgets.js";
import { gameList } from "./games.js";

export async function render(view, route) {
  const id = route.parts[0];
  const ply = route.query.get("ply");
  view.innerHTML = spinner("Running Stockfish… a game not analysed yet takes about half a minute.");
  const depth = state.cfg.depth;
  const doc = await getJSON(`/api/game?user=${encodeURIComponent(state.user)}&selector=${encodeURIComponent(id || "last")}&depth=${depth}`);

  // older / newer game, from the list the Games page uses
  let nav = "";
  try {
    const rows = await gameList();
    const i = rows.findIndex((r) => String(r.id) === String(doc.meta.game_id));
    if (i >= 0) {
      const newer = rows[i - 1], older = rows[i + 1];
      nav = `<div class="seg">` +
        (older ? `<a class="btn ghost" href="#/game/${esc(older.id)}" title="${esc(older.date)} vs ${esc(older.opponent)}">‹ older</a>` : "") +
        `<a class="btn ghost" href="#/games">all games</a>` +
        (newer ? `<a class="btn ghost" href="#/game/${esc(newer.id)}" title="${esc(newer.date)} vs ${esc(newer.opponent)}">newer ›</a>` : "") +
        `</div>`;
    }
  } catch (e) { /* navigation is a convenience */ }

  view.innerHTML = `<div id="gm-doc"></div>`;
  renderDoc(view.querySelector("#gm-doc"), doc);
  if (nav) view.querySelector("h1").insertAdjacentHTML("afterend", `<div class="actions">${nav}</div>`);
  if (ply != null && ply !== "") {
    window.dispatchEvent(new CustomEvent("rv-goto", { detail: +ply }));
  } else {
    window.scrollTo({ top: 0 });
  }
}
