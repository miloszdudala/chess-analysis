// Overview: where you stand, how you compare with players at your rating,
// and what to work on.

import { esc, getJSON, setStatus, spinner, who } from "../api.js";
import { renderDoc } from "../widgets.js";

export async function render(view) {
  view.innerHTML = spinner("Comparing your games with players at your rating…");
  const doc = await getJSON(`/api/overview?${who()}`);
  renderDoc(view, doc);
  const h1 = view.querySelector("h1");
  if (h1) {
    h1.insertAdjacentHTML("beforeend",
      ` <a href="https://www.chess.com/member/${esc(doc.meta.player)}" target="_blank" rel="noopener">↗</a>`);
  }
  setStatus("");
}
