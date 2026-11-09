// Shared state, fetch helpers and small formatting functions.

export const $ = (id) => document.getElementById(id);
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const state = {
  cfg: null,
  user: "",
  format: "rapid",
};

const KEY_USER = "chess-analysis:user";
const KEY_FORMAT = "chess-analysis:format";
const KEY_THEME = "chess-analysis:theme";

function load(key, fallback = "") {
  try {
    // keys were "chess-analyzer:*" before the rename; read those as a fallback
    return localStorage.getItem(key)
      ?? localStorage.getItem(key.replace("chess-analysis:", "chess-analyzer:"))
      ?? fallback;
  } catch (e) { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
}

export function initState(cfg) {
  state.cfg = cfg;
  state.user = load(KEY_USER) || cfg.user || "";
  state.format = load(KEY_FORMAT, "rapid") || "rapid";
}
export function setUser(name) { state.user = (name || "").trim(); save(KEY_USER, state.user); }
export function setFormat(fmt) { state.format = fmt; save(KEY_FORMAT, fmt); }
export function theme() { return load(KEY_THEME, ""); }
export function setTheme(t) { save(KEY_THEME, t); }

// query string for the account + format every page reports on
export function who(extra = {}) {
  const p = new URLSearchParams({ user: state.user, format: state.format, ...extra });
  return p.toString();
}

async function parse(r) {
  let d;
  try { d = await r.json(); } catch (e) { throw new Error(`HTTP ${r.status}`); }
  if (!r.ok || (d && d.error)) throw new Error((d && d.error) || `HTTP ${r.status}`);
  return d;
}
export async function getJSON(url) { return parse(await fetch(url)); }
export async function postJSON(url) { return parse(await fetch(url, { method: "POST" })); }

// --- formatting ------------------------------------------------------------------

export const pct = (x, digits = 0) => (x == null ? "—" : `${(100 * x).toFixed(digits)}%`);
export const signedPct = (x) => (x == null ? "—" : `${x >= 0 ? "+" : "−"}${Math.abs(100 * x).toFixed(0)}%`);
export function evalText(cp) {
  if (cp == null) return "—";
  if (Math.abs(cp) >= 9000) {
    const n = 10000 - Math.abs(cp);
    return `${cp > 0 ? "+" : "−"}M${n > 0 && n < 100 ? n : ""}`;
  }
  const v = cp / 100;
  return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1);
}
export function winProb(cp) { return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1); }
export function fmtDur(sec) {
  if (sec == null) return "";
  if (sec < 90) return `~${Math.max(1, Math.round(sec))}s`;
  if (sec < 5400) return `~${Math.round(sec / 60)} min`;
  return `~${(sec / 3600).toFixed(1)} h`;
}
export function fmtClock(sec) {
  if (sec == null) return "";
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
export const resultMark = (o) => (o === "win" ? "✓" : o === "loss" ? "✗" : "=");
export const resultCls = (o) => (o === "win" ? "res-win" : o === "loss" ? "res-loss" : "res-draw");

export function spinner(msg) { return `<p class="text"><span class="spinner"></span>${esc(msg)}</p>`; }
export function errorBox(msg) { return `<p class="text" style="color:var(--loss)">${esc(msg)}</p>`; }

let statusTimer = null;
export function setStatus(msg, isErr = false, busy = false) {
  const s = $("status");
  if (!s) return;
  clearTimeout(statusTimer);
  s.className = "status" + (isErr ? " err" : "");
  s.innerHTML = busy ? `<span class="spinner"></span>${esc(msg)}` : esc(msg || "");
}
export function flashStatus(msg, ms = 4000) {
  setStatus(msg);
  statusTimer = setTimeout(() => setStatus(""), ms);
}

// change the address without re-rendering (a page tracking its own state)
export function replaceHash(hash) { history.replaceState(null, "", hash); }
