// Peers: the rating corpus — you against players at your rating, or every rating.

import { esc, getJSON, postJSON, replaceHash, setStatus, spinner, state, who } from "../api.js";
import { renderDoc } from "../widgets.js";

export async function render(view, route) {
  let scope = route.query.get("scope") === "ladder" ? "ladder" : "peers";
  let windowSize = +(route.query.get("window") || 70);
  view.innerHTML =
    `<div class="page-head"><div class="grow"><h1>Peers</h1><p class="sub-title">Other players' ` +
    `${esc((state.cfg && state.cfg.corpus && state.cfg.corpus.label) || "")} games, analysed by the same engine at ` +
    `the same depth as yours, so every comparison here is on equal terms. <b>At my rating</b> sets you against ` +
    `players rated close to you; <b>Every rating</b> shows what changes as rating rises. ` +
    `<a class="guide-link" href="#/guide?s=peers">How this is measured →</a></p></div>` +
    `<div class="seg" id="pr-scope"><button data-s="peers">At my rating</button><button data-s="ladder">Every rating</button></div></div>` +
    `<div class="controls"><div class="field" id="pr-win-f"><label>Players within</label><select id="pr-win">` +
    [50, 70, 100, 150].map((w) => `<option value="${w}"${w === windowSize ? " selected" : ""}>± ${w} of your rating</option>`).join("") +
    `</select></div><div class="field"><label>Expand by</label><select id="pr-n">` +
    [50, 100, 250, 500].map((n) => `<option value="${n}"${n === 100 ? " selected" : ""}>${n} games</option>`).join("") +
    `</select></div><button class="btn" id="pr-expand" title="Download more players' games and analyse them, thinnest rating ranges first">⊕ Expand the corpus</button>` +
    `<span class="mut" id="pr-size" style="font-size:.84rem;align-self:center"></span></div><div id="pr-doc"></div>`;
  const $q = (s) => view.querySelector(s);

  async function size() {
    try {
      const d = await getJSON("/api/corpus");
      const thin = (d.coverage || []).slice().sort((a, b) => a.samples - b.samples)[0];
      $q("#pr-size").textContent = `${d.games} games · ${d.players} players · ${d.samples} game sides at depth ${d.depth}` +
        (thin ? ` · thinnest range ${thin.band}–${thin.band + d.band_size - 1} (${thin.samples})` : "");
      if (d.job && d.job.running) poll();
    } catch (e) { /* an empty corpus is not an error */ }
  }
  async function poll() {
    const d = await getJSON("/api/corpus");
    const j = d.job || {};
    const btn = $q("#pr-expand");
    if (!btn) return;
    if (j.running) {
      btn.disabled = true;
      setStatus(`Expanding the corpus… ${j.note || ""} (${j.elapsed}s)`, false, true);
      setTimeout(() => poll().catch(() => {}), 1500);
      return;
    }
    btn.disabled = false;
    if (j.error) setStatus("Expanding failed: " + j.error, true);
    else if (j.finished) setStatus(`Added ${j.banked || 0} games (${j.analysed || 0} analysed). Reload the view to include them.`);
    size();
  }
  $q("#pr-expand").onclick = async () => {
    try {
      await postJSON(`/api/corpus/expand?user=${encodeURIComponent(state.user)}&n=${$q("#pr-n").value}`);
      poll();
    } catch (e) { setStatus(e.message, true); }
  };

  async function load() {
    view.querySelectorAll("#pr-scope button").forEach((b) => b.classList.toggle("on", b.dataset.s === scope));
    $q("#pr-win-f").style.display = scope === "peers" ? "" : "none";
    replaceHash(`#/peers?scope=${scope}${scope === "peers" ? "&window=" + windowSize : ""}`);
    const host = $q("#pr-doc");
    host.innerHTML = spinner(scope === "peers" ? "Comparing you with players at your rating…" : "Comparing every rating range…");
    try {
      const doc = await getJSON(`/api/brackets?${who({ scope, window: windowSize })}`);
      renderDoc(host, doc);
    } catch (e) {
      host.innerHTML = `<div class="empty"><h2>Nothing to show yet</h2><p>${esc(e.message)}</p></div>`;
    }
  }
  view.querySelectorAll("#pr-scope button").forEach((b) => { b.onclick = () => { scope = b.dataset.s; load(); }; });
  $q("#pr-win").onchange = () => { windowSize = +$q("#pr-win").value; load(); };
  size();
  load();
}
