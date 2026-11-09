// Extras: lighter stats about your games. For now, the countries you have played.

import { esc, getJSON, pct, spinner, state, who } from "../api.js";
import { COUNTRIES, VIEWBOX } from "../worldmap.js";

const STEPS = 5;                       // colour steps on the map, light -> dark

// A flag from an ISO code (regional-indicator letters); Chess.com's X* codes have none.
const flag = (code) => (/^[A-Z]{2}$/.test(code) && code[0] !== "X"
  ? String.fromCodePoint(...[...code].map((c) => 0x1f1a5 + c.charCodeAt(0))) : "");
const nameOf = (c) => c.name || (COUNTRIES[c.code] && COUNTRIES[c.code].name) || c.code;
const record = (r) => `${r.win}–${r.draw}–${r.loss}`;
const plural = (n, w) => `${n} ${n === 1 ? w : w.replace(/y$/, "ie") + "s"}`;

// Bin edges spread evenly on a log scale, so one country you play all the time
// doesn't wash every other one out to the lightest step.
function edges(max) {
  const out = [];
  for (let i = 0; i <= STEPS; i++) {
    const e = Math.round(Math.pow(max, i / STEPS));
    if (!out.length || e > out[out.length - 1]) out.push(e);
  }
  return out;                          // bin k holds games in (out[k-1], out[k]], bin 0 is exactly out[0]
}
const binOf = (n, e) => { let k = 0; while (k < e.length - 1 && n > e[k]) k++; return k; };
// Steps are fixed mixes of the accent into the panel, so the ramp follows the theme.
const fillFor = (k, bins) => `color-mix(in oklab, var(--accent) ${Math.round(32 + (68 * k) / Math.max(1, bins - 1))}%, var(--panel))`;

export async function render(view) {
  view.innerHTML = spinner("Collecting your opponents' countries…");
  const d = await getJSON(`/api/countries?${who()}`);
  const fmt = (state.cfg && state.format) ? ` ${state.format}` : "";

  // Several Chess.com codes can share one shape (England, Scotland… in the UK).
  const shapes = {};
  for (const c of d.countries) {
    if (!c.map) continue;
    const s = shapes[c.map] || (shapes[c.map] = { code: c.map, games: 0, win: 0, draw: 0, loss: 0, parts: [] });
    s.games += c.games; s.win += c.win; s.draw += c.draw; s.loss += c.loss;
    s.parts.push(c);
  }
  const max = Math.max(1, ...Object.values(shapes).map((s) => s.games));
  const e = edges(max);
  const unmapped = d.countries.filter((c) => !(c.map && COUNTRIES[c.map]));

  const paths = Object.entries(COUNTRIES).map(([code, c]) => {
    const s = shapes[code];
    const style = s ? ` style="fill:${fillFor(binOf(s.games, e), e.length)}"` : "";
    return `<path d="${c.d}" data-c="${code}" class="${s ? "on" : ""}"${style}/>`;
  }).join("");
  const dots = Object.entries(COUNTRIES).filter(([code, c]) => c.dot && shapes[code]).map(([code, c]) =>
    `<circle cx="${c.dot[0]}" cy="${c.dot[1]}" r="4" data-c="${code}" class="on" ` +
    `style="fill:${fillFor(binOf(shapes[code].games, e), e.length)}"/>`).join("");

  const legend = e.map((hi, k) => {
    const lo = k ? e[k - 1] + 1 : hi;
    return `<span class="wm-key"><i style="background:${fillFor(k, e.length)}"></i>${lo === hi ? hi : `${lo}–${hi}`}</span>`;
  }).join("");

  const rows = d.countries.map((c) =>
    `<tr data-c="${esc(c.map || "")}"><td>${flag(c.code)} ${esc(nameOf(c))}</td><td class="num">${c.games}</td>` +
    `<td class="num">${c.win}</td><td class="num">${c.draw}</td><td class="num">${c.loss}</td>` +
    `<td class="num">${pct(c.score)}</td></tr>`).join("");

  view.innerHTML =
    `<h1>Extras</h1><p class="sub-title">Lighter stats about your${esc(fmt)} games.</p>` +
    `<h2>Countries you've played</h2>` +
    `<p class="text">${plural(d.countries.length, "country")} across ${plural(d.total, "game")}` +
    (d.unknown ? ` — ${plural(d.unknown, "game")} against opponents whose country isn't known yet ` +
      `(it fills in as your games sync)` : "") +
    (unmapped.length ? (() => {
      const n = unmapped.reduce((k, c) => k + c.games, 0);
      return `; ${plural(n, "game")} against players listed as ${unmapped.map((c) => esc(nameOf(c))).join(" or ")} ` +
        `${n === 1 ? "is" : "are"} in the table only`;
    })() : "") +
    `. The darker the country, the more games. Point at one for your record.</p>` +
    `<div class="wm-wrap"><svg class="wm" viewBox="${VIEWBOX.join(" ")}" role="img" ` +
    `aria-label="World map of the countries you've played, shaded by number of games">${paths}${dots}</svg>` +
    `<div class="wm-tip" hidden></div></div>` +
    `<div class="wm-legend"><span class="lead">Games</span>${legend}</div>` +
    (rows ? `<div class="tablewrap"><table class="wm-table"><thead><tr><th>Country</th><th class="num">Games</th><th class="num">Won</th>` +
      `<th class="num">Drawn</th><th class="num">Lost</th><th class="num">Score</th></tr></thead><tbody>${rows}</tbody></table></div>` : "");

  const wrap = view.querySelector(".wm-wrap"), tip = view.querySelector(".wm-tip"), svg = view.querySelector("svg.wm");

  function tipHTML(code) {
    const s = shapes[code], name = (COUNTRIES[code] && COUNTRIES[code].name) || code;
    if (!s) return `<b>${flag(code)} ${esc(name)}</b><div class="mut">No games yet</div>`;
    const line = (r) => `${plural(r.games, "game")} · ${record(r)} · score ${pct((r.win + r.draw / 2) / r.games)}`;
    const parts = s.parts.length > 1 || s.parts[0].code !== code
      ? s.parts.map((p) => `<div class="wm-part">${esc(nameOf(p))}: ${line(p)}</div>`).join("") : "";
    return `<b>${flag(code)} ${esc(name)}</b><div>${line(s)}</div>` +
      `<div class="mut wm-wdl">won–drawn–lost</div>${parts}`;
  }
  function highlight(code) {
    svg.querySelectorAll(".hl").forEach((n) => n.classList.remove("hl"));
    if (code) svg.querySelectorAll(`[data-c="${code}"]`).forEach((n) => { n.classList.add("hl"); n.parentNode.appendChild(n); });
  }
  function show(code, ev) {
    tip.innerHTML = tipHTML(code);
    tip.hidden = false;
    const box = wrap.getBoundingClientRect();
    const x = ev.clientX - box.left, y = ev.clientY - box.top;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.min(Math.max(4, x + 14), box.width - w - 4)}px`;
    tip.style.top = `${y + 18 + h > box.height ? Math.max(4, y - h - 12) : y + 18}px`;
  }
  svg.addEventListener("pointermove", (ev) => {
    const code = ev.target.dataset && ev.target.dataset.c;
    if (!code) { tip.hidden = true; highlight(null); return; }
    highlight(code);
    show(code, ev);
  });
  svg.addEventListener("pointerleave", () => { tip.hidden = true; highlight(null); });
  view.querySelectorAll(".wm-table tbody tr").forEach((tr) => {
    tr.onmouseenter = () => highlight(tr.dataset.c);
    tr.onmouseleave = () => highlight(null);
  });
}
