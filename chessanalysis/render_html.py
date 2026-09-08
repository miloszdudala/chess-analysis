"""Render a Document to a static HTML page.

One handler per widget `type`. This is the *default* renderer; a JS frontend
can consume the same Document JSON instead. Adding a widget type = add a
handler here (and, later, a frontend component).
"""
from __future__ import annotations

import html

from .document import Document

SERIES_COLORS = ["#5b9c4a", "#4a7f9c", "#9c7a4a", "#8a4a9c"]


def esc(x) -> str:
    return html.escape(str(x))


def _pct(n, total) -> str:
    return f"{100 * n / total:.0f}%" if total else "—"


def _bar(w, d, l) -> str:
    total = w + d + l
    if not total:
        return ""
    pw, pd, pl = (100 * x / total for x in (w, d, l))
    return (f'<div class="bar"><span class="w" style="width:{pw}%"></span>'
            f'<span class="d" style="width:{pd}%"></span>'
            f'<span class="l" style="width:{pl}%"></span></div>')


# --- widget handlers --------------------------------------------------------

def _cards(w) -> str:
    out = []
    for it in w["items"]:
        sub = f'<div class="sub">{esc(it["sub"])}</div>' if it.get("sub") else ""
        out.append(f'<div class="card"><div class="big">{esc(it["value"])}</div>'
                   f'<div class="lbl">{esc(it["label"])}</div>{sub}</div>')
    return '<div class="cards">' + "".join(out) + "</div>"


def _cell(c) -> str:
    if isinstance(c, dict) and "bar" in c:
        return _bar(*c["bar"])
    return esc(c)


def _table(w) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in w["columns"])
    body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in row) + "</tr>"
                   for row in w["rows"])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _wdl_table(w) -> str:
    rows = []
    for r in w["rows"]:
        win, draw, loss = r["win"], r["draw"], r["loss"]
        t = win + draw + loss
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in [
            esc(r["label"]), t, win, draw, loss, _pct(win, t), _bar(win, draw, loss),
        ]) + "</tr>")
    head = "".join(f"<th>{esc(c)}</th>"
                   for c in [w["label_col"], "Games", "W", "D", "L", "Win%", ""])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _drilltable(w) -> str:
    # static export: the columnar table only — the per-row game drill-down is
    # interactive (opens each game's board) and lives in the web app.
    head = "".join(f"<th>{esc(c)}</th>" for c in w["columns"])
    body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in r["cells"])
                   + "</tr>" for r in w["rows"])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _line(w) -> str:
    svgs = []
    for i, s in enumerate(w["series"]):
        pts = s["points"]
        ys = [p["y"] if isinstance(p, dict) else p for p in pts]
        if len(ys) < 2:
            continue
        lo, hi = min(ys), max(ys)
        rng = (hi - lo) or 1
        coords = " ".join(
            f"{100 * j / (len(ys) - 1):.2f},{100 - 100 * (y - lo) / rng:.2f}"
            for j, y in enumerate(ys))
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        svgs.append(f'<polyline points="{coords}" style="stroke:{color}"/>')
    if not svgs:
        return ""
    return ('<svg viewBox="0 0 100 100" preserveAspectRatio="none" class="spark">'
            + "".join(svgs) + "</svg>")


def _eval(w) -> str:
    plies = w["plies"]
    if len(plies) < 2:
        return ""
    CLAMP = 1000
    n = len(plies)

    def xy(i, cp):
        x = 100 * i / (n - 1)
        cp = max(-CLAMP, min(CLAMP, cp))
        y = 50 - 50 * (cp / CLAMP)   # cp>0 (white) -> nearer top
        return x, y

    curve = [xy(i, p["cp"]) for i, p in enumerate(plies)]
    line_pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in curve)
    # white-territory polygon: under the curve down to the bottom edge
    area = (f"0,100 " + " ".join(f"{x:.2f},{y:.2f}" for x, y in curve) + " 100,100")
    # a flag is drawn one ply back, on the eval the mover was looking at, so a
    # red dot sits at the top of the cliff rather than at the bottom of it
    dots = "".join(
        f'<circle cx="{xy(i - 1, plies[i - 1]["cp"])[0]:.2f}" '
        f'cy="{xy(i - 1, plies[i - 1]["cp"])[1]:.2f}" r="1.6" '
        f'class="m-{p.get("label","ok")}"/>'
        for i, p in enumerate(plies)
        if i > 0 and p.get("label") in ("blunder", "mistake", "inaccuracy"))
    return (f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" class="evalg">'
            f'<rect width="100" height="100" class="ev-black"/>'
            f'<polygon points="{area}" class="ev-white"/>'
            f'<line x1="0" y1="50" x2="100" y2="50" class="ev-mid"/>'
            f'<polyline points="{line_pts}" class="ev-line"/>{dots}</svg>')


def _board(w) -> str:
    inner = w.get("svg") or ""
    cap = f'<figcaption>{esc(w["caption"])}</figcaption>' if w.get("caption") else ""
    return f'<figure class="board">{inner}{cap}</figure>'


def _tree_node(node) -> str:
    t = node["w"] + node["d"] + node["l"]
    wr = f'{round(100 * node["w"] / t)}%' if t else ""
    head = (f'<span class="mv">{esc(node["move"])}</span>'
            f'<span class="ct">{node["count"]}</span>'
            f'{_bar(node["w"], node["d"], node["l"])}'
            f'<span class="wr">{wr}</span>')
    cls = "mine" if node.get("mine") else "opp"
    if node.get("children"):
        kids = "".join(_tree_node(c) for c in node["children"])
        return (f'<details class="{cls}"><summary>{head}</summary>'
                f'<div class="kids">{kids}</div></details>')
    return f'<div class="leaf {cls}">{head}</div>'


def _movetree(w) -> str:
    return f'<div class="tree">{"".join(_tree_node(c) for c in w["children"])}</div>'


def _ranking(w) -> str:
    items = []
    for i, r in enumerate(w["rows"], 1):
        sub = f'<span class="rk-sub">{esc(r["sub"])}</span>' if r.get("sub") else ""
        items.append(f'<li><span class="rk-rank">{i}</span>'
                     f'<span class="rk-label">{esc(r["label"])}</span>{sub}'
                     f'<span class="rk-val">{esc(r["value"])}</span></li>')
    title = f'<h3>{esc(w["title"])}</h3>' if w.get("title") else ""
    return f'<div class="ranking">{title}<ol>{"".join(items)}</ol></div>'


def _group(w) -> str:
    inner = "".join(render_widget(c) for c in w["widgets"])
    title = f'<h3>{esc(w["title"])}</h3>' if w.get("title") else ""
    return f'{title}<div class="group group-{w.get("layout","row")}">{inner}</div>'


def _recent(w) -> str:
    # Engine-backed and interactive; only meaningful in the web app.
    return ('<p class="text">Recent-game analysis is interactive — '
            'open the web app (<code>python webapp.py</code>) to browse it.</p>')


def _conversion(w) -> str:
    return ('<p class="text">Conversion &amp; stage analysis is engine-backed — '
            'open the web app (<code>python webapp.py</code>) to view it.</p>')


def _text(w) -> str:
    return f'<p class="text">{w["body"]}</p>'


def _verdict(w) -> str:
    # static export: the reason dropdown is interactive (web app only); show the
    # current verdict as a card + sentence.
    manual = ' <span class="vd-manual">manually set</span>' if w.get("manual") else ""
    if w.get("anomalous"):
        manual += ' <span class="vd-manual">⚑ anomalous — not counted</span>'
    sub = f'<div class="vd-sub">{esc(w["sub"])}</div>' if w.get("sub") else ""
    return (f'<div class="verdict"><div class="vd-label">{esc(w["label"])}{manual}</div>'
            f'<div class="vd-headline">{esc(w["headline"])}</div>{sub}'
            f'<p class="text vd-detail">{esc(w["detail"])}</p></div>')


def _review(w) -> str:
    # Fully interactive (board navigation + engine arrows); web app only.
    return ('<p class="text">The move-by-move board explorer is interactive — '
            'open the web app (<code>python webapp.py</code>) to play through it.</p>')


def _barstack(w) -> str:
    pal = w["palette"]
    # legend follows the bar's segment order, not the palette dict's key order
    order = [s["name"] for s in w["rows"][0]["segments"]] if w["rows"] else list(pal)
    legend = "".join(
        f'<span class="bs-leg"><i style="background:{pal.get(name, "#ccc")}"></i>{esc(name)}</span>'
        for name in order)
    rows = []
    for r in w["rows"]:
        total = sum(s["value"] for s in r["segments"]) or 1
        segs = "".join(
            f'<span class="bs-seg" style="width:{100 * s["value"] / total:.1f}%;'
            f'background:{pal.get(s["name"], "#ccc")}" title="{esc(s["name"])}: {s["value"]}">'
            f'{s["value"] if 100 * s["value"] / total > 7 else ""}</span>'
            for s in r["segments"] if s["value"] > 0)
        note = f'<span class="bs-note">{esc(r["note"])}</span>' if r.get("note") else ""
        rows.append(f'<div class="bs-row"><span class="bs-label">{esc(r["label"])}</span>'
                    f'<span class="bs-bar">{segs}</span>{note}</div>')
    title = f'<div class="bs-title">{esc(w["title"])}</div>' if w.get("title") else ""
    return (f'<div class="barstack">{title}{"".join(rows)}'
            f'<div class="bs-legend">{legend}</div></div>')


def _donut(w) -> str:
    segs = [s for s in w["segments"] if s["value"] > 0]
    total = sum(s["value"] for s in segs) or 1
    circles, cumulative = [], 0.0
    for s in segs:
        length = 100 * s["value"] / total
        circles.append(
            f'<circle class="dn-seg" cx="21" cy="21" r="15.915" fill="none" '
            f'stroke="{s["color"]}" stroke-width="5" '
            f'stroke-dasharray="{length:.2f} {100 - length:.2f}" '
            f'stroke-dashoffset="{25 - cumulative:.2f}">'
            f'<title>{esc(s["name"])}: {s["value"]}</title></circle>')
        cumulative += length
    center = (f'<text class="dn-c" x="21" y="20.5">{esc(w["center"])}</text>'
              if w.get("center") else "")
    sub = (f'<text class="dn-s" x="21" y="25.5">{esc(w["sub"])}</text>'
           if w.get("sub") else "")
    legend = "".join(
        f'<span class="bs-leg"><i style="background:{s["color"]}"></i>'
        f'{esc(s["name"])} {s["value"]}</span>' for s in segs)
    return (f'<div class="donut"><svg viewBox="0 0 42 42" class="dn-svg">'
            f'{"".join(circles)}{center}{sub}</svg>'
            f'<div class="bs-legend">{legend}</div></div>')


def _timeline(w) -> str:
    col = {"win": "var(--win)", "draw": "var(--draw)", "loss": "var(--loss)"}
    cells = "".join(
        f'<span class="tl-cell" style="background:{col.get(it["outcome"], "#ccc")}" '
        f'title="{esc(it.get("label", ""))}"></span>' for it in w["items"])
    title = f'<div class="bs-title">{esc(w["title"])}</div>' if w.get("title") else ""
    return f'<div class="timeline">{title}<div class="tl-row">{cells}</div></div>'


_HANDLERS = {
    "cards": _cards, "table": _table, "wdl_table": _wdl_table,
    "drilltable": _drilltable, "line": _line,
    "eval": _eval, "board": _board, "group": _group, "ranking": _ranking,
    "movetree": _movetree, "recent": _recent, "conversion": _conversion,
    "text": _text, "verdict": _verdict, "review": _review, "barstack": _barstack,
    "donut": _donut, "timeline": _timeline,
}


def render_widget(w) -> str:
    fn = _HANDLERS.get(w.get("type"))
    return fn(w) if fn else f"<!-- unknown widget {w.get('type')} -->"


_CSS = """
  :root {
    --bg:#fbfaf7; --panel:#ffffff; --ink:#23211d; --mut:#9b958a; --line:#ece8e0;
    --accent:#1d6f6a; --win:#3f7d5a; --draw:#d6d0c4; --loss:#c1573f;
    --mono:ui-monospace,"SF Mono",Menlo,monospace;
  }
  * { box-sizing:border-box; }
  body { font:15px/1.55 ui-sans-serif,system-ui,sans-serif; background:var(--bg);
         color:var(--ink); margin:0; padding:2rem 1.1rem; }
  .wrap { max-width:960px; margin:0 auto; }
  h1 { font-size:1.7rem; font-weight:600; letter-spacing:-.01em; margin:0 0 .15rem; }
  h2 { font-size:.78rem; font-weight:600; letter-spacing:.13em; text-transform:uppercase;
       color:var(--mut); margin:2.4rem 0 .8rem; padding-bottom:.4rem;
       border-bottom:1px solid var(--line); }
  .cat-head { font-size:1.15rem; font-weight:600; letter-spacing:-.01em; color:var(--ink);
              margin:2.8rem 0 .2rem; }
  .cat-head:first-of-type { margin-top:1.4rem; }
  .cat-head + h2 { margin-top:1rem; }
  h3 { font-size:.72rem; font-weight:600; letter-spacing:.1em; text-transform:uppercase;
       color:var(--mut); margin:0 0 .6rem; }
  .sub-title { color:var(--mut); margin:0 0 1.5rem; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:.7rem; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px;
          padding:1rem 1.1rem; }
  .card .big { font:600 1.7rem/1.1 var(--mono); letter-spacing:-.02em; }
  .card .lbl { color:var(--mut); font-size:.7rem; text-transform:uppercase;
               letter-spacing:.08em; margin-top:.35rem; }
  .card .sub { color:var(--mut); font-size:.78rem; margin-top:.15rem; }
  table { width:100%; border-collapse:collapse; background:var(--panel);
          border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  th,td { padding:.55rem .8rem; text-align:left; border-bottom:1px solid var(--line); }
  tbody tr:last-child td { border-bottom:0; }
  th { color:var(--mut); font-size:.7rem; font-weight:600; text-transform:uppercase;
       letter-spacing:.06em; }
  td { font-variant-numeric:tabular-nums; }
  td:nth-child(n+2):not(:last-child), th:nth-child(n+2):not(:last-child) { text-align:center; }
  .bar { display:flex; height:8px; border-radius:4px; overflow:hidden; min-width:90px;
         background:var(--line); }
  .bar .w { background:var(--win); } .bar .d { background:var(--draw); } .bar .l { background:var(--loss); }
  .group { display:flex; gap:1rem; flex-wrap:wrap; }
  .group-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); }
  .ranking { background:var(--panel); border:1px solid var(--line); border-radius:12px;
             padding:.9rem 1rem; }
  .ranking ol { list-style:none; margin:0; padding:0; }
  .ranking li { display:flex; align-items:baseline; gap:.5rem; padding:.35rem 0;
                border-bottom:1px solid var(--line); }
  .ranking li:last-child { border-bottom:0; }
  .ranking .rk-rank { font:var(--mono); color:var(--mut); font-size:.75rem; width:1.2rem; }
  .ranking .rk-label { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ranking .rk-sub { color:var(--mut); font-size:.72rem; }
  .ranking .rk-val { font:600 .95rem var(--mono); }
  /* interactive rating chart (web app) */
  .chart-wrap { position:relative; background:var(--panel); border:1px solid var(--line);
                border-radius:12px; padding:.5rem .4rem .2rem; }
  .chart-wrap svg { display:block; width:100%; height:auto; touch-action:none; }
  .chart-grid { stroke:var(--line); stroke-width:1; }
  .chart-wrap svg text { fill:var(--mut); font-size:10px; font-family:var(--mono); }
  .chart-area { fill:var(--accent); opacity:.08; }
  .chart-area.muted { opacity:.04; }
  .chart-line { fill:none; stroke:var(--accent); stroke-width:1.6; }
  .chart-line.muted { stroke:#b9b4a8; stroke-width:1.2; }
  .chart-line-ma { fill:none; stroke:var(--accent); stroke-width:2.4; stroke-linejoin:round; }
  .chart-guide { stroke:var(--mut); stroke-dasharray:3 3; }
  .chart-dot { fill:var(--panel); stroke:var(--accent); stroke-width:2; }
  .chart-brush { fill:var(--accent); opacity:.12; }
  .chart-hint { color:var(--mut); font-size:.7rem; text-align:right; padding:.1rem .5rem .2rem; }
  .chart-toolbar { display:flex; gap:.35rem; margin-bottom:.5rem; align-items:center;
          flex-wrap:wrap; }
  .gbtn { background:var(--panel); border:1px solid var(--line); color:var(--mut);
          border-radius:7px; padding:.2rem .65rem; font:inherit; font-size:.78rem; cursor:pointer; }
  .gbtn.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  /* toolbar checkbox (e.g. "show anomalous") + the rows it reveals */
  .tb-check { display:flex; align-items:center; gap:.3rem; margin-left:.5rem;
          color:var(--mut); font-size:.78rem; cursor:pointer; }
  .tb-check input { accent-color:var(--accent); margin:0; }
  .tb-check.tb-hidden { display:none; }
  tr.rr-flagged td { opacity:.55; }
  .rr-flag { color:var(--accent); margin-right:.3rem; }
  /* opening move tree */
  .tree { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:.5rem .6rem; }
  .tree details > summary, .tree .leaf { display:flex; align-items:center; gap:.55rem;
          padding:.25rem .35rem; border-radius:7px; list-style:none; }
  .tree details > summary { cursor:pointer; }
  .tree summary::-webkit-details-marker { display:none; }
  .tree summary::before { content:"▸"; color:var(--mut); font-size:.7rem; width:.8rem;
          display:inline-block; }
  .tree details[open] > summary::before { content:"▾"; }
  .tree .leaf::before { content:""; width:.8rem; display:inline-block; }
  .tree details > summary:hover { background:var(--bg); }
  .tree .kids { margin-left:1rem; border-left:1px solid var(--line); padding-left:.3rem; }
  .tree .mv { font-family:var(--mono); font-weight:600; min-width:3.4rem; }
  .tree .opp .mv { font-weight:500; color:var(--mut); }
  .tree .ct { color:var(--mut); font-size:.8rem; font-variant-numeric:tabular-nums; min-width:2rem; }
  .tree .wr { color:var(--mut); font-size:.8rem; margin-left:auto; font-variant-numeric:tabular-nums; }
  .tree .bar { width:90px; min-width:90px; flex:0 0 auto; }
  /* recent games (web app) */
  .recent-tbl tr.rrow { cursor:pointer; }
  .recent-tbl tr.rrow:hover td { background:var(--bg); }
  .recent-tbl td.res-win { color:var(--win); font-weight:600; }
  .recent-tbl td.res-loss { color:var(--loss); font-weight:600; }
  .conv-held { color:var(--win); } .conv-lost { color:var(--loss); }
  /* win/loss reasons drill-down (web app) */
  .reasons-head { font-size:.78rem; font-weight:600; letter-spacing:.13em;
                  text-transform:uppercase; color:var(--mut); margin:1.1rem 0 .4rem; }
  details.reason { border:1px solid var(--line); border-radius:9px; background:var(--panel);
                   margin:.4rem 0; overflow:hidden; }
  details.reason > summary { cursor:pointer; list-style:none; padding:.6rem .85rem;
                   display:flex; align-items:center; gap:.6rem; }
  details.reason > summary::-webkit-details-marker { display:none; }
  details.reason > summary::before { content:"▸"; color:var(--mut); font-size:.8rem; }
  details.reason[open] > summary::before { content:"▾"; }
  details.reason[open] > summary { border-bottom:1px solid var(--line); }
  .reason-label { font-weight:600; }
  .reason-count { font-variant-numeric:tabular-nums; color:var(--accent); font-weight:600; }
  .reason-sub { color:var(--mut); font-size:.82rem; margin-left:auto; }
  .reason-stat { padding:.5rem .85rem; color:var(--mut); font-size:.82rem;
                 background:var(--bg); }
  .reason-games { margin:0; }
  .reason-games td.reason-note { color:var(--mut); font-size:.85rem; }
  /* game verdict + manual reason override (web app) */
  .verdict { border:1px solid var(--line); border-radius:10px; background:var(--panel);
             padding:.8rem 1rem .3rem; }
  .vd-top { display:flex; align-items:flex-start; gap:1rem; flex-wrap:wrap; }
  .vd-main { flex:1; min-width:12rem; }
  .vd-label { font-size:.68rem; text-transform:uppercase; letter-spacing:.08em;
              color:var(--mut); }
  .vd-headline { font-size:1.15rem; font-weight:600; letter-spacing:-.01em; margin-top:.1rem; }
  .vd-sub { color:var(--mut); font-size:.82rem; margin-top:.15rem; }
  .vd-pick { display:flex; flex-direction:column; gap:.25rem; font-size:.68rem;
             text-transform:uppercase; letter-spacing:.08em; color:var(--mut); }
  .vd-pick select { text-transform:none; letter-spacing:normal; font:inherit;
                    background:var(--bg); color:var(--ink); border:1px solid var(--line);
                    border-radius:8px; padding:.35rem .5rem; }
  .vd-manual { display:inline-block; margin-left:.4rem; color:var(--accent);
               font-weight:600; letter-spacing:normal; text-transform:none; }
  .vd-detail { margin:.5rem 0 .4rem; }
  .reason-games tr.rrow td:first-child { padding-left:1.4rem; }
  /* "anomalous" checkbox: the game stays in the history, leaves the stats */
  .vd-flag { display:flex; align-items:center; gap:.35rem; margin-top:.4rem;
             text-transform:none; letter-spacing:normal; font-size:.75rem;
             cursor:pointer; }
  .vd-flag input { accent-color:var(--accent); margin:0; }
  .vd-cheat { margin:0 0 .7rem; padding:.5rem .7rem; border-radius:8px;
    background:rgba(193,87,63,.09); border:1px solid var(--loss);
    color:var(--ink); font-size:.85rem; }
  .verdict.vd-anomalous { border-color:var(--accent); }
  .verdict.vd-anomalous .vd-headline { text-decoration:line-through;
             text-decoration-color:var(--mut); }
  .gf-count { display:block; color:var(--accent); font-size:.72rem; margin-top:.25rem; }
  /* drill-down table: rows expand to the games behind them (web app) */
  table.drilltable th:first-child, table.drilltable td.dt-caret { width:1.2rem;
                   padding-right:0; }
  table.drilltable tr.dt-row.dt-open { cursor:pointer; }
  table.drilltable tr.dt-row.dt-open:hover td { background:var(--bg); }
  td.dt-caret { color:var(--mut); font-size:.75rem; transition:transform .12s; }
  tr.dt-exp td.dt-caret { color:var(--accent); }
  tr.dt-games > td { padding:0 0 .5rem 1.2rem; background:var(--bg); }
  tr.dt-games table { margin:0; }
  .chart-tip { position:absolute; pointer-events:none; background:var(--ink); color:#fff;
               padding:.4rem .55rem; border-radius:7px; font-size:.75rem; white-space:nowrap;
               transform:translate(-50%,-130%); opacity:0; transition:opacity .07s; z-index:4; }
  .chart-tip b { font-family:var(--mono); }
  .chart-tip .up { color:#7fd3a8; } .chart-tip .dn { color:#f0a08c; }
  /* eval graph — static (.evalg) and interactive (.evalc) */
  .evalg { width:100%; height:120px; border-radius:10px; background:#2c2a26; }
  .eval-host { position:relative; }
  svg.evalc { display:block; width:100%; height:auto; }
  .ev-black { fill:#2c2a26; } .ev-white { fill:#e7e3da; }
  .ev-mid { stroke:#ffffff33; stroke-width:1; vector-effect:non-scaling-stroke; }
  .ev-grid { stroke:#88888855; stroke-width:1; vector-effect:non-scaling-stroke; }
  .ev-zero { stroke:#777; stroke-width:1.4; vector-effect:non-scaling-stroke; }
  .ev-line { fill:none; stroke:#5a5a5a; stroke-width:1.4; vector-effect:non-scaling-stroke; }
  svg.evalc text.ev-ax { fill:var(--mut); font-size:10px; font-family:var(--mono); }
  svg.evalc circle.ev-dot { stroke:#fff; stroke-width:1.2; vector-effect:non-scaling-stroke;
                            transition:r .08s; }
  svg.evalc circle.ev-dot:hover { r:7.5; }
  .evc-legend { display:flex; flex-wrap:wrap; gap:.5rem .9rem; margin:0 0 .4rem; font-size:.82rem; }
  .evc-key { display:inline-flex; align-items:center; gap:.35rem; cursor:pointer;
             background:none; border:0; padding:.1rem .15rem; color:var(--mut);
             font:inherit; border-radius:5px; }
  .evc-n { color:var(--mut); font-size:.9em; }
  .evc-key:hover { color:var(--ink); }
  .evc-key.off { opacity:.4; text-decoration:line-through; }
  .evc-sw { width:.85rem; height:.32rem; border-radius:2px; display:inline-block; }
  .evc-sw.dashed { height:0; border-radius:0; background:transparent;
                   border-top:2px dashed currentColor; }
  circle.m-blunder { fill:var(--loss); } circle.m-mistake { fill:#d99a3a; }
  circle.m-inaccuracy { fill:#e0b020; }
  .spark { width:100%; height:64px; }
  .spark polyline { fill:none; stroke:var(--accent); stroke-width:1.5; vector-effect:non-scaling-stroke; }
  /* stacked-bar chart */
  .barstack { background:var(--panel); border:1px solid var(--line); border-radius:12px;
              padding:.85rem 1rem; }
  .bs-title { font-size:.8rem; color:var(--mut); margin-bottom:.5rem; }
  .bs-row { display:flex; align-items:center; gap:.7rem; margin:.4rem 0; }
  .bs-label { flex:0 0 7.5rem; font-size:.8rem; line-height:1.15; color:var(--ink); }
  .bs-bar { flex:1; display:flex; height:22px; border-radius:5px; overflow:hidden;
            background:var(--line); }
  .bs-seg { display:flex; align-items:center; justify-content:center; color:#fff;
            font:600 .72rem var(--mono); min-width:0; transition:width .2s; }
  .bs-note { flex:0 0 auto; font:600 .76rem var(--mono); color:var(--mut);
             min-width:4.2rem; text-align:right; font-variant-numeric:tabular-nums; }
  .bs-legend { display:flex; flex-wrap:wrap; gap:.3rem .9rem; margin-top:.65rem; }
  .bs-leg { display:inline-flex; align-items:center; gap:.35rem; font-size:.72rem;
            color:var(--mut); text-transform:capitalize; }
  .bs-leg i { width:10px; height:10px; border-radius:2px; }
  /* donut (ring) chart */
  .donut { background:var(--panel); border:1px solid var(--line); border-radius:12px;
           padding:.9rem 1rem; display:flex; flex-direction:column; align-items:center; }
  .dn-svg { width:150px; height:150px; transform:rotate(-90deg); }
  .dn-seg { transition:stroke-dasharray .3s; }
  .dn-c { transform:rotate(90deg); transform-origin:21px 21px; text-anchor:middle;
          fill:var(--ink); font:600 7px var(--mono); }
  .dn-s { transform:rotate(90deg); transform-origin:21px 21px; text-anchor:middle;
          fill:var(--mut); font:2.6px ui-sans-serif,system-ui,sans-serif; }
  /* results timeline strip */
  .timeline { background:var(--panel); border:1px solid var(--line); border-radius:12px;
              padding:.85rem 1rem; }
  .tl-row { display:flex; flex-wrap:wrap; gap:3px; }
  .tl-cell { width:14px; height:14px; border-radius:3px; }
  /* interactive review board (web app) */
  .rv { display:flex; gap:1rem; flex-wrap:wrap; align-items:flex-start; }
  .rv-main { display:flex; flex-direction:column; gap:.45rem;
             flex:1 1 320px; max-width:440px; min-width:280px; }
  .rv-evalbar { position:relative; height:22px; width:100%; border-radius:6px;
                overflow:hidden; background:#2c2a26; }
  .rv-fill { position:absolute; top:0; bottom:0; left:0; background:#e7e3da;
             transition:width .18s ease; }
  .rv-en { position:absolute; top:0; bottom:0; display:flex; align-items:center;
           font:600 .72rem var(--mono); padding:0 .5rem; z-index:1; }
  .rv-en-l { left:0; color:#2c2a26; } .rv-en-r { right:0; color:#e7e3da; }
  .rv-board { width:100%; }
  .rv-svg { width:100%; height:auto; display:block; border-radius:8px;
            box-shadow:0 1px 6px #0001; }
  .rv-l { fill:#ecd9b6; } .rv-d { fill:#b08a5e; }
  /* last-move highlight, tinted by how good the move was */
  .rv-hl { fill:#cdd06a !important; }
  .rv-hl-best { fill:#8fb96a !important; }
  .rv-hl-inaccuracy { fill:#dac35a !important; }
  .rv-hl-mistake { fill:#e0a85a !important; }
  .rv-hl-blunder { fill:#d98a72 !important; }
  .rv-sel { fill:#7fb2dd !important; }   /* picked-up piece (wins over last-move) */
  .rv-p { text-anchor:middle; pointer-events:none; }
  .rv-pw { fill:#fafafa; stroke:#3a342c; stroke-width:.8px; }
  .rv-pb { fill:#2b2824; stroke:#0c0b0a; stroke-width:.6px; }
  .rv-co { fill:#00000055; font:600 9px var(--mono); pointer-events:none; }
  .rv-side { flex:1 1 240px; min-width:230px; display:flex; flex-direction:column; gap:.6rem; }
  .rv-players { display:flex; justify-content:space-between; font-size:.82rem; color:var(--mut); }
  .rv-info { background:var(--panel); border:1px solid var(--line); border-radius:10px;
             padding:.55rem .7rem; font-size:.9rem; min-height:1.2rem; }
  .rv-mv { font:600 .95rem var(--mono); }
  .rv-tag { font-size:.74rem; padding:.05rem .45rem; border-radius:5px; margin-left:.3rem;
            white-space:nowrap; }
  .rv-tag b { font-family:var(--mono); }
  .rv-best { color:#3f9d5a; } .rv-blunder { color:#d0493b; }
  .rv-mistake { color:#e08a2b; } .rv-inaccuracy { color:#c69a16; }
  .rv-tag.rv-best { background:#3f9d5a22; } .rv-tag.rv-blunder { background:#d0493b22; }
  .rv-tag.rv-mistake { background:#e08a2b22; } .rv-tag.rv-inaccuracy { background:#e0b02022; }
  .rv-engine { background:var(--panel); border:1px solid var(--line); border-radius:10px;
               padding:.5rem .7rem; display:flex; flex-wrap:wrap; align-items:center; gap:.3rem .8rem; }
  .rv-eh { font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; color:var(--mut);
           width:100%; }
  .rv-line { display:inline-flex; align-items:center; gap:.35rem; font-size:.85rem;
             font-variant-numeric:tabular-nums; }
  .rv-line i { width:9px; height:9px; border-radius:2px; display:inline-block; }
  .rv-line b { font-family:var(--mono); }
  .rv-nav { display:flex; gap:.3rem; }
  .rv-nav button { flex:1; background:var(--panel); border:1px solid var(--line);
                   border-radius:8px; padding:.35rem 0; font-size:.95rem; cursor:pointer;
                   color:var(--ink); }
  .rv-nav button:hover { background:var(--bg); border-color:var(--accent); }
  .rv-tip { color:var(--mut); font-size:.72rem; text-align:center; padding:.1rem .2rem; }
  .rv-varbar { display:flex; gap:.3rem; }
  .rv-varbar button { flex:1; background:var(--accent); border:1px solid var(--accent);
                      color:#fff; border-radius:8px; padding:.35rem .4rem; font:inherit;
                      font-size:.78rem; cursor:pointer; }
  .rv-varbar button:hover { filter:brightness(1.08); }
  .rv-tag.rv-live { color:#fff; background:var(--accent); }
  .rv-moves { display:grid; grid-template-columns:auto 1fr 1fr; gap:.05rem .3rem;
              background:var(--panel); border:1px solid var(--line); border-radius:10px;
              padding:.5rem .6rem; max-height:230px; overflow-y:auto;
              font-size:.85rem; align-content:start; }
  .rv-no { color:var(--mut); font-family:var(--mono); font-size:.78rem; text-align:right;
           padding-right:.2rem; }
  .rv-m { cursor:pointer; padding:.1rem .35rem; border-radius:5px; font-family:var(--mono); }
  .rv-m:hover { background:var(--bg); }
  .rv-m.on { background:var(--accent); color:#fff; }
  .rv-m.m-blunder { color:#d0493b; } .rv-m.m-mistake { color:#e08a2b; }
  .rv-m.m-inaccuracy { color:#c69a16; }
  .rv-m.on.m-blunder, .rv-m.on.m-mistake, .rv-m.on.m-inaccuracy { color:#fff; }
  figure.board { margin:0; background:var(--panel); border:1px solid var(--line);
                 border-radius:12px; padding:.6rem; width:240px; }
  figure.board svg { width:100%; height:auto; border-radius:6px; }
  figure.board figcaption { color:var(--mut); font-size:.82rem; margin-top:.4rem; }
  .text { color:var(--mut); }
  footer { color:var(--mut); font-size:.78rem; margin-top:3rem; text-align:center; }
  a { color:var(--accent); }
"""


def css() -> str:
    """The report stylesheet — single source of truth (CLI page + web app)."""
    return _CSS


def render_sections(doc: Document) -> str:
    """Just the section widgets (no page shell) — for embedding / the web app."""
    body = []
    current_cat = None
    for s in doc.sections:
        if s.category and s.category != current_cat:
            body.append(f'<div class="cat-head">{esc(s.category)}</div>')
            current_cat = s.category
        if s.title:
            body.append(f"<h2>{esc(s.title)}</h2>")
        body.extend(render_widget(w) for w in s.widgets)
    return "".join(body)


def render_document(doc: Document) -> str:
    sub = f'<p class="sub-title">{esc(doc.subtitle)}</p>' if doc.subtitle else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(doc.title)}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<h1>{esc(doc.title)}</h1>{sub}
{render_sections(doc)}
<footer>Generated by chessanalysis · {esc(doc.mode)} mode</footer>
</div></body></html>"""
