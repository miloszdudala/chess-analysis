// Stats: the descriptive report — results, form, the clock, and the engine
// insights over all of your games.

import { esc, getJSON, replaceHash, spinner, who } from "../api.js";
import { renderDoc } from "../widgets.js";

export async function render(view, route) {
  view.innerHTML = spinner("Building your report…");
  const doc = await getJSON(`/api/player?${who()}`);
  let category = route.query.get("cat") || null;

  function draw() {
    view.innerHTML = `<h1>${esc(doc.title)}</h1><p class="sub-title">${esc(doc.subtitle)}</p>` +
      `<div id="st-chips" class="chips"></div><div id="st-body"></div>`;
    const cats = renderDoc(view.querySelector("#st-body"), doc, { category, head: false });
    const chips = view.querySelector("#st-chips");
    if (cats.length > 1) {
      const pill = (label, val, on) => `<button class="chip${on ? " on" : ""}" data-cat="${esc(val)}">${esc(label)}</button>`;
      chips.innerHTML = `<span class="lead">Show</span>` + pill("Everything", "", !category) +
        cats.map((c) => pill(c, c, category === c)).join("");
      chips.querySelectorAll(".chip").forEach((b) => {
        b.onclick = () => {
          category = b.dataset.cat || null;
          replaceHash(`#/stats${category ? "?cat=" + encodeURIComponent(category) : ""}`);
          draw();
        };
      });
    }
  }
  draw();
}
