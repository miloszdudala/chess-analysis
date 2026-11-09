// Boot, routing, and everything that lives in the app bar.
//
// Routes are hashes (#/train?kind=missed), so every view has an address:
// the back button works, and a report can link straight to a page.

import {
  $, esc, fmtDur, flashStatus, getJSON, initState, postJSON, setFormat, setStatus,
  setTheme, setUser, state, theme,
} from "./api.js";

const PAGES = {
  overview: () => import("./pages/overview.js"),
  games: () => import("./pages/games.js"),
  game: () => import("./pages/game.js"),
  openings: () => import("./pages/openings.js"),
  train: () => import("./pages/train.js"),
  stats: () => import("./pages/stats.js"),
  peers: () => import("./pages/peers.js"),
  scout: () => import("./pages/scout.js"),
  extras: () => import("./pages/extras.js"),
  guide: () => import("./pages/guide.js"),
};
const TABS = [["overview", "Overview"], ["games", "Games"], ["openings", "Openings"],
  ["train", "Train"], ["stats", "Stats"], ["peers", "Peers"], ["scout", "Scout"], ["extras", "Extras"], ["guide", "Guide"]];
const TAB_OF = { game: "games" };
const FORMAT_LABELS = { rapid: "Rapid", blitz: "Blitz", bullet: "Bullet", daily: "Daily" };

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  return { page: parts[0] || "overview", parts: parts.slice(1), query: new URLSearchParams(qs || "") };
}

let renderSeq = 0;
async function route() {
  const r = parseHash();
  const load = PAGES[r.page] || PAGES.overview;
  const seq = ++renderSeq;
  renderTabs(TAB_OF[r.page] || r.page);
  setStatus("");
  if (!state.user && r.page !== "guide") {
    $("view").innerHTML = `<div class="empty"><h2>Whose games?</h2><p>Type a Chess.com account in the box at the top right.</p></div>`;
    return;
  }
  const mod = await load();
  if (seq !== renderSeq) return;            // the user moved on meanwhile
  const view = $("view");
  view.innerHTML = "";
  try {
    await mod.render(view, r);
  } catch (e) {
    if (seq === renderSeq) setStatus(e.message, true);
  }
}

function renderTabs(active) {
  $("tabs").innerHTML = TABS.map(([k, label]) =>
    `<a href="#/${k}" class="${k === active ? "active" : ""}" data-tab="${k}">${label}` +
    (k === "train" && trainBadge ? `<span class="badge">${trainBadge}</span>` : "") + `</a>`).join("");
}

// --- the training badge ---------------------------------------------------------------
let trainBadge = 0;
async function refreshTrainBadge() {
  if (!state.user) return;
  try {
    const t = await getJSON(`/api/train/summary?user=${encodeURIComponent(state.user)}`);
    trainBadge = t ? t.due + Math.min(t.new, t.new_left_today) : 0;
    renderTabs((TAB_OF[parseHash().page] || parseHash().page));
  } catch (e) { /* not fatal */ }
}

// --- syncing --------------------------------------------------------------------------
// An account is synced when the page opens and when you switch to one not yet
// pulled this session. Reload to force a fresh pull.
const synced = new Set();
async function syncUser(user) {
  const key = user.toLowerCase();
  if (synced.has(key)) return;
  synced.add(key);
  setStatus(`Syncing ${user} from Chess.com…`, false, true);
  try {
    const d = await postJSON(`/api/sync?user=${encodeURIComponent(user)}`);
    let msg = d.fresh ? "" : `${d.new} new game${d.new === 1 ? "" : "s"}`;
    if (d.banned && d.banned.length) {
      msg += `${msg ? " · " : ""}${d.banned.length} opponent${d.banned.length === 1 ? "" : "s"} ` +
        `banned for fair play (their games are excluded and the rating they cost added back)`;
    }
    flashStatus(msg || "Up to date.");
  } catch (e) {
    setStatus(`Sync failed (${e.message}) — showing the games already stored.`, true);
  }
}

// --- background analysis ----------------------------------------------------------------
let jobTimer = null;
let jobWasRunning = false;

function renderJob(s) {
  const line = $("job-line"), fill = $("job-fill");
  if (s.running) {
    const pct = s.total ? Math.round((100 * (s.done || 0)) / s.total) : 0;
    fill.style.width = `${pct}%`;
    line.classList.add("on");
    const left = s.eta ? ` · ${fmtDur(s.eta)} left` : "";
    line.innerHTML = `<span class="spinner"></span>Analysing your games — ${esc(s.stage || "starting")} · ` +
      `${s.done || 0}/${s.total}${left}`;
  } else if (s.error) {
    line.classList.add("on");
    line.innerHTML = `Background analysis stopped: ${esc(s.error)} <button id="job-retry">retry</button>`;
    const b = $("job-retry"); if (b) b.onclick = startJob;
    fill.style.width = "0";
  } else if (jobWasRunning && s.finished && s.done > 0) {
    fill.style.width = "100%";
    line.classList.add("on");
    line.innerHTML = `Every game is analysed. <button id="job-reload">refresh this page</button>`;
    const b = $("job-reload"); if (b) b.onclick = () => { line.classList.remove("on"); route(); };
    setTimeout(() => { fill.style.width = "0"; }, 1500);
    refreshTrainBadge();
  } else {
    line.classList.remove("on");
    fill.style.width = "0";
  }
}

async function pollJob() {
  clearTimeout(jobTimer);
  try {
    const s = await getJSON(`/api/job/analysis?user=${encodeURIComponent(state.user)}`);
    const mine = (s.key || "").toLowerCase() === state.user.toLowerCase();
    if (s.running && !mine) { jobTimer = setTimeout(pollJob, 1500); return; }   // another account winding down
    if (!s.running && !s.finished && s.total) { startJob(); return; }
    renderJob(s);
    if (s.running) { jobWasRunning = true; jobTimer = setTimeout(pollJob, 2000); }
    else jobWasRunning = false;
  } catch (e) { jobTimer = setTimeout(pollJob, 6000); }
}

async function startJob() {
  if (!state.user) return;
  try { await postJSON(`/api/job/analysis?user=${encodeURIComponent(state.user)}`); } catch (e) { /* shown by poll */ }
  jobWasRunning = true;
  pollJob();
}

// --- delegated interactions -------------------------------------------------------------
function bindGlobal() {
  document.addEventListener("click", (e) => {
    const row = e.target.closest("[data-game-id].rrow");
    if (row && !e.target.closest("a")) {
      const ply = row.dataset.ply;
      location.hash = `#/game/${row.dataset.gameId}` + (ply !== "" && ply != null ? `?ply=${ply}` : "");
      return;
    }
    const jump = e.target.closest("[data-goto]");
    if (jump) { window.dispatchEvent(new CustomEvent("rv-goto", { detail: +jump.dataset.goto })); return; }
    const dt = e.target.closest("tr.dt-row.dt-open");
    if (dt) {
      const sub = dt.parentNode.querySelector(`tr.dt-games[data-for="${dt.dataset.row}"]`);
      if (sub) {
        sub.hidden = !sub.hidden;
        dt.classList.toggle("dt-exp", !sub.hidden);
        const caret = dt.querySelector(".dt-caret");
        if (caret) caret.textContent = sub.hidden ? "▸" : "▾";
      }
    }
  });
  document.addEventListener("change", async (e) => {
    const sel = e.target.closest(".verdict .vd-select");
    if (sel) {
      const box = sel.closest(".verdict");
      sel.disabled = true;
      try {
        await postJSON(`/api/verdict?game=${encodeURIComponent(box.dataset.gameId)}&reason=${encodeURIComponent(sel.value)}`);
        box.querySelector(".vd-headline").textContent = sel.options[sel.selectedIndex].textContent;
        flashStatus("Reason saved — it counts in your win/loss breakdown from now on.");
      } catch (err) { setStatus("Could not save the reason: " + err.message, true); }
      finally { sel.disabled = false; }
      return;
    }
    const anom = e.target.closest(".verdict .vd-anom");
    if (anom) {
      const card = anom.closest(".verdict"), on = anom.checked;
      anom.disabled = true;
      try {
        await postJSON(`/api/flag?game=${encodeURIComponent(card.dataset.gameId)}&flag=${on ? "anomaly" : ""}`);
        card.classList.toggle("vd-anomalous", on);
        flashStatus(on ? "Flagged as anomalous — it leaves every statistic but stays in your history."
                       : "Unflagged — it counts again.");
      } catch (err) { anom.checked = !on; setStatus("Could not save the flag: " + err.message, true); }
      finally { anom.disabled = false; }
    }
  });
}

// --- boot --------------------------------------------------------------------------------
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
}

(async function boot() {
  applyTheme(theme());
  let cfg;
  try { cfg = await getJSON("/api/config"); }
  catch (e) { setStatus("The server isn't answering: " + e.message, true); return; }
  initState(cfg);
  $("f-user").value = state.user;
  $("f-format").innerHTML = (cfg.formats || ["rapid", "blitz", "bullet"]).map((f) =>
    `<option value="${f}"${f === state.format ? " selected" : ""}>${FORMAT_LABELS[f] || f}</option>`).join("");
  $("theme").onclick = () => {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next); setTheme(next);
  };
  bindGlobal();
  $("f-format").onchange = () => { setFormat($("f-format").value); route(); };
  $("f-user").onchange = async () => {
    setUser($("f-user").value);
    if (!state.user) { route(); return; }
    await syncUser(state.user);
    startJob();
    refreshTrainBadge();
    route();
  };
  window.addEventListener("hashchange", route);
  window.addEventListener("train-changed", refreshTrainBadge);
  renderTabs(parseHash().page);
  if (state.user) {
    await syncUser(state.user);
    startJob();
    refreshTrainBadge();
  }
  route();
})();
