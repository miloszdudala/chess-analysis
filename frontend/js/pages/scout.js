// Scout: prepare for an opponent from their recent games.

import { esc, getJSON, spinner, who } from "../api.js";
import { renderDoc } from "../widgets.js";
import { mountExplorer } from "./openings.js";

const KEY = "chess-analysis:scouted";
function recent() { try { return JSON.parse(localStorage.getItem(KEY) || localStorage.getItem("chess-analyzer:scouted") || "[]"); } catch (e) { return []; } }
function remember(name) {
  try {
    const list = [name, ...recent().filter((n) => n.toLowerCase() !== name.toLowerCase())].slice(0, 8);
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch (e) { /* private mode */ }
}

export async function render(view, route) {
  const [name, sub, color] = route.parts;
  if (name && sub === "explore") {
    mountExplorer(view, {
      db: name, color: color === "black" ? "black" : "white",
      moves: (route.query.get("moves") || "").split(",").filter(Boolean),
      hashFor: (c, m) => `#/scout/${encodeURIComponent(name)}/explore/${c}${m.length ? "?moves=" + m.join(",") : ""}`,
      title: `${name}'s repertoire`,
    });
    view.querySelector(".page-head").insertAdjacentHTML("beforebegin",
      `<div class="actions"><a class="btn ghost" href="#/scout/${esc(name)}">‹ back to the report</a></div>`);
    return;
  }
  const months = +(route.query.get("months") || 6);
  view.innerHTML =
    `<div class="page-head"><div class="grow"><h1>Scout</h1><p class="sub-title">Name an opponent: their ` +
    `recent games are downloaded and read for preparation — what they open with, how their games end, ` +
    `how they handle the clock (beside players at their rating), and how your own games went in the ` +
    `lines they choose.</p></div></div>` +
    `<form class="controls" id="sc-form"><div class="field"><label>Opponent</label>` +
    `<input id="sc-name" placeholder="chess.com account" value="${esc(name || "")}" autocomplete="off" spellcheck="false"></div>` +
    `<div class="field"><label>Look back</label><select id="sc-months">` +
    [3, 6, 12].map((m) => `<option value="${m}"${m === months ? " selected" : ""}>${m} months</option>`).join("") +
    `</select></div><button class="btn primary" type="submit">Scout</button></form>` +
    `<div class="sc-recent" id="sc-recent"></div><div id="sc-doc"></div>`;
  const $q = (s) => view.querySelector(s);
  const prev = recent();
  if (prev.length) {
    $q("#sc-recent").innerHTML = `<span class="lead mut" style="font-size:.72rem;text-transform:uppercase;letter-spacing:.08em">Recent</span>` +
      prev.map((n) => `<a class="chip" href="#/scout/${esc(n)}">${esc(n)}</a>`).join("");
  }
  $q("#sc-form").onsubmit = (e) => {
    e.preventDefault();
    const n = $q("#sc-name").value.trim();
    if (n) location.hash = `#/scout/${encodeURIComponent(n)}?months=${$q("#sc-months").value}`;
  };
  if (!name) { $q("#sc-name").focus(); return; }
  const host = $q("#sc-doc");
  host.innerHTML = spinner(`Downloading ${name}'s last ${months} months from Chess.com…`);
  const doc = await getJSON(`/api/scout?${who({ opp: name, months })}`);
  remember(name);
  renderDoc(host, doc);
  if (doc.meta.note) host.insertAdjacentHTML("afterbegin", `<p class="status err">${esc(doc.meta.note)}</p>`);
}
