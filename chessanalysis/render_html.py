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
    dots = "".join(
        f'<circle cx="{xy(i, p["cp"])[0]:.2f}" cy="{xy(i, p["cp"])[1]:.2f}" r="1.6" '
        f'class="m-{p.get("label","ok")}"/>'
        for i, p in enumerate(plies)
        if p.get("label") in ("blunder", "mistake", "inaccuracy"))
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


_HANDLERS = {
    "cards": _cards, "table": _table, "wdl_table": _wdl_table, "line": _line,
    "eval": _eval, "board": _board, "group": _group, "ranking": _ranking,
    "movetree": _movetree, "recent": _recent, "conversion": _conversion,
    "text": _text,
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
  .chart-line { fill:none; stroke:var(--accent); stroke-width:1.6; }
  .chart-guide { stroke:var(--mut); stroke-dasharray:3 3; }
  .chart-dot { fill:var(--panel); stroke:var(--accent); stroke-width:2; }
  .chart-brush { fill:var(--accent); opacity:.12; }
  .chart-hint { color:var(--mut); font-size:.7rem; text-align:right; padding:.1rem .5rem .2rem; }
  .chart-toolbar { display:flex; gap:.35rem; margin-bottom:.5rem; }
  .gbtn { background:var(--panel); border:1px solid var(--line); color:var(--mut);
          border-radius:7px; padding:.2rem .65rem; font:inherit; font-size:.78rem; cursor:pointer; }
  .gbtn.on { background:var(--accent); border-color:var(--accent); color:#fff; }
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
  .chart-tip { position:absolute; pointer-events:none; background:var(--ink); color:#fff;
               padding:.4rem .55rem; border-radius:7px; font-size:.75rem; white-space:nowrap;
               transform:translate(-50%,-130%); opacity:0; transition:opacity .07s; z-index:4; }
  .chart-tip b { font-family:var(--mono); }
  .chart-tip .up { color:#7fd3a8; } .chart-tip .dn { color:#f0a08c; }
  /* eval graph — static (.evalg) and interactive (.evalc) */
  .evalg { width:100%; height:120px; border-radius:10px; background:#2c2a26; }
  .eval-host { position:relative; }
  svg.evalc { display:block; width:100%; height:auto; border-radius:10px; }
  .ev-black { fill:#2c2a26; } .ev-white { fill:#e7e3da; }
  .ev-mid { stroke:#ffffff33; stroke-width:1; vector-effect:non-scaling-stroke; }
  .ev-line { fill:none; stroke:#888; stroke-width:1; vector-effect:non-scaling-stroke; }
  circle.m-blunder { fill:var(--loss); } circle.m-mistake { fill:#d99a3a; }
  circle.m-inaccuracy { fill:#e0b020; }
  .spark { width:100%; height:64px; }
  .spark polyline { fill:none; stroke:var(--accent); stroke-width:1.5; vector-effect:non-scaling-stroke; }
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
    for s in doc.sections:
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
