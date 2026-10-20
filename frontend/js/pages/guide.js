// Guide: what every number in the app means. `?s=<id>` scrolls to a section,
// so any page can link straight to the definition it relies on.

import { getJSON, spinner } from "../api.js";
import { renderDoc } from "../widgets.js";

export async function render(view, route) {
  view.innerHTML = spinner("Loading the guide…");
  const doc = await getJSON("/api/guide");
  renderDoc(view, doc);
  const ids = (doc.meta && doc.meta.ids) || [];
  view.querySelectorAll("h2").forEach((h, i) => { if (ids[i]) h.id = `guide-${ids[i]}`; });
  const target = route.query.get("s");
  const el = target && view.querySelector(`#guide-${CSS.escape(target)}`);
  if (el) el.scrollIntoView({ block: "start" });
  else window.scrollTo({ top: 0 });
}
