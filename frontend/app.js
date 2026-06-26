"use strict";

const $ = (id) => document.getElementById(id);
const state = { cfg: null, mode: "player", games: null };

const MODE_LABELS = { player: "Player report", game: "Game review", compare: "Compare" };

async function getJSON(url) {
  const r = await fetch(url);
  const data = await r.json();
  if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function setStatus(msg, isErr = false, busy = false) {
  const s = $("status");
  s.className = "status" + (isErr ? " err" : "");
  s.innerHTML = busy ? `<span class="spinner"></span>${msg}` : (msg || "");
}

// --- controls per mode ------------------------------------------------------

function field(label, inner) {
  return `<div class="field"><label>${label}</label>${inner}</div>`;
}

function renderControls() {
  const c = $("controls");
  const user = state.cfg.user || "";
  if (state.mode === "player") {
    c.innerHTML =
      field("Username", `<input id="f-user" value="${user}" placeholder="chess.com handle">`) +
      `<button class="go" id="run">Generate report</button>`;
    $("run").onclick = () => run();
  } else if (state.mode === "game") {
    c.innerHTML =
      field("Game", `<select id="f-game"><option value="last">Loading games…</option></select>`) +
      field("Engine depth", `<input id="f-depth" type="number" min="6" max="22" value="${state.cfg.depth}">`) +
      `<button class="go" id="run">Analyze game</button>`;
    $("run").onclick = () => run();
    loadGames();
  } else if (state.mode === "compare") {
    c.innerHTML =
      field("Player A", `<input id="f-a" value="${user}">`) +
      field("Player B", `<input id="f-b" placeholder="opponent handle">`) +
      `<button class="go" id="run">Compare</button>`;
    $("run").onclick = () => run();
  }
}

async function loadGames() {
  try {
    const games = await getJSON("/api/games?user=" + encodeURIComponent(state.cfg.user || ""));
    state.games = games;
    const sel = $("f-game");
    const opts = [`<option value="last">⭐ Most recent</option>`].concat(
      games.map((g) => {
        const mark = g.outcome === "win" ? "✓" : g.outcome === "loss" ? "✗" : "=";
        return `<option value="${g.id}">${mark} ${g.date} · ${g.white} vs ${g.black} ` +
               `(${g.result}) · ${g.time_class}</option>`;
      })
    );
    sel.innerHTML = opts.join("");
  } catch (e) {
    setStatus("Could not load games: " + e.message, true);
  }
}

// --- run a mode -------------------------------------------------------------

async function run() {
  let url;
  if (state.mode === "player") {
    url = "/api/player?user=" + encodeURIComponent($("f-user").value.trim());
    setStatus("Building report…", false, true);
  } else if (state.mode === "game") {
    const sel = $("f-game").value, depth = $("f-depth").value;
    url = `/api/game?selector=${encodeURIComponent(sel)}&depth=${depth}`;
    setStatus("Running Stockfish… first analysis of a game can take a few seconds.", false, true);
  } else {
    url = `/api/compare?a=${encodeURIComponent($("f-a").value.trim())}` +
          `&b=${encodeURIComponent($("f-b").value.trim())}`;
    setStatus("Comparing…", false, true);
  }
  $("run").disabled = true;
  try {
    const data = await getJSON(url);
    renderResult(data);
    setStatus("");
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    $("run").disabled = false;
  }
}

function renderResult(data) {
  const sub = data.subtitle ? `<p class="sub-title">${data.subtitle}</p>` : "";
  let link = "";
  if (data.meta && data.meta.url) {
    link = ` <a href="${data.meta.url}" target="_blank" rel="noopener">↗ on Chess.com</a>`;
  }
  $("result").innerHTML = `<h1>${data.title}${link}</h1>${sub}${data.html}`;
  document.title = data.title + " · Chess Analyzer";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// --- init -------------------------------------------------------------------

function renderTabs() {
  $("tabs").innerHTML = state.cfg.modes.map((m) =>
    `<button class="tab ${m === state.mode ? "active" : ""}" data-mode="${m}">` +
    `${MODE_LABELS[m] || m}</button>`).join("");
  document.querySelectorAll(".tab").forEach((b) => {
    b.onclick = () => { state.mode = b.dataset.mode; renderTabs(); renderControls();
                        $("result").innerHTML = ""; setStatus(""); };
  });
}

(async function init() {
  try {
    state.cfg = await getJSON("/api/config");
  } catch (e) {
    setStatus("Backend not reachable: " + e.message, true);
    return;
  }
  renderTabs();
  renderControls();
  if (state.cfg.user) run();   // auto-load the player report
})();
