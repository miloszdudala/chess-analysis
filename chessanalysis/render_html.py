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
        f'<circle cx="{xy(i, p["cp"])[0]:.2f}" cy="{xy(i, p["cp"])[1]:.2f}" r="1.4" '
        f'class="m-{p.get("label","ok")}"/>'
        for i, p in enumerate(plies) if p.get("label") in ("blunder", "mistake"))
    return (f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" class="evalg">'
            f'<rect width="100" height="100" class="ev-black"/>'
            f'<polygon points="{area}" class="ev-white"/>'
            f'<line x1="0" y1="50" x2="100" y2="50" class="ev-mid"/>'
            f'<polyline points="{line_pts}" class="ev-line"/>{dots}</svg>')


def _board(w) -> str:
    inner = w.get("svg") or ""
    cap = f'<figcaption>{esc(w["caption"])}</figcaption>' if w.get("caption") else ""
    return f'<figure class="board">{inner}{cap}</figure>'


def _group(w) -> str:
    inner = "".join(render_widget(c) for c in w["widgets"])
    title = f'<h3>{esc(w["title"])}</h3>' if w.get("title") else ""
    return f'{title}<div class="group group-{w.get("layout","row")}">{inner}</div>'


def _text(w) -> str:
    return f'<p class="text">{w["body"]}</p>'


_HANDLERS = {
    "cards": _cards, "table": _table, "wdl_table": _wdl_table, "line": _line,
    "eval": _eval, "board": _board, "group": _group, "text": _text,
}


def render_widget(w) -> str:
    fn = _HANDLERS.get(w.get("type"))
    return fn(w) if fn else f"<!-- unknown widget {w.get('type')} -->"


_CSS = """
  :root { --w:#5b9c4a; --d:#b8b8b8; --l:#c44; --bg:#161512; --card:#262421;
          --txt:#e8e6e3; --mut:#9a9690; --accent:#5b9c4a; }
  * { box-sizing:border-box; }
  body { font:15px/1.5 system-ui,sans-serif; background:var(--bg); color:var(--txt);
         margin:0; padding:2rem 1rem; }
  .wrap { max-width:920px; margin:0 auto; }
  h1 { font-size:1.6rem; margin:0 0 .2rem; }
  h2 { font-size:1.1rem; margin:2.2rem 0 .6rem; color:var(--mut);
       text-transform:uppercase; letter-spacing:.05em; }
  h3 { font-size:.95rem; margin:1rem 0 .5rem; color:var(--mut); }
  .sub-title { color:var(--mut); margin:0 0 1.5rem; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:.8rem; }
  .card { background:var(--card); border-radius:10px; padding:1rem; }
  .card .big { font-size:1.8rem; font-weight:700; }
  .card .lbl { color:var(--mut); font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; }
  .card .sub { color:var(--mut); font-size:.8rem; margin-top:.2rem; }
  table { width:100%; border-collapse:collapse; background:var(--card);
          border-radius:10px; overflow:hidden; }
  th,td { padding:.5rem .7rem; text-align:left; border-bottom:1px solid #00000030; }
  th { color:var(--mut); font-size:.8rem; text-transform:uppercase; }
  td:nth-child(n+2):not(:last-child), th:nth-child(n+2):not(:last-child) { text-align:center; }
  .bar { display:flex; height:10px; border-radius:5px; overflow:hidden; min-width:80px; }
  .bar .w { background:var(--w); } .bar .d { background:var(--d); } .bar .l { background:var(--l); }
  .spark { width:100%; height:64px; }
  .spark polyline { fill:none; stroke-width:1.5; vector-effect:non-scaling-stroke; }
  .evalg { width:100%; height:120px; border-radius:8px; background:var(--card); }
  .ev-black { fill:#3a3835; } .ev-white { fill:#d9d9d4; }
  .ev-mid { stroke:#0006; stroke-width:.5; vector-effect:non-scaling-stroke; }
  .ev-line { fill:none; stroke:#1116; stroke-width:1; vector-effect:non-scaling-stroke; }
  circle.m-blunder { fill:var(--l); } circle.m-mistake { fill:#e0a341; }
  .group { display:flex; gap:1rem; flex-wrap:wrap; }
  .group-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); }
  figure.board { margin:0; background:var(--card); border-radius:10px; padding:.6rem; width:240px; }
  figure.board svg { width:100%; height:auto; border-radius:6px; }
  figure.board figcaption { color:var(--mut); font-size:.82rem; margin-top:.4rem; }
  footer { color:var(--mut); font-size:.8rem; margin-top:3rem; text-align:center; }
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
