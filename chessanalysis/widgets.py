"""Widget vocabulary — the backend↔frontend data contract.

Every metric returns one of these JSON-serializable dicts (or a list of them).
A renderer (render_html.py today, a JS frontend tomorrow) maps `type` -> view.
Adding a chart type = add a builder here + one renderer; nothing else changes.

Widgets are deliberately multi-series from the start so comparison mode is just
"more series in the same widget" — no new widget types needed.
"""
from __future__ import annotations


def cards(items: list[dict]) -> dict:
    """items: [{"value":.., "label":.., "sub":?}]"""
    return {"type": "cards", "items": items}


def card(value, label, sub=None) -> dict:
    d = {"value": value, "label": label}
    if sub is not None:
        d["sub"] = sub
    return d


def table(columns: list[str], rows: list[list]) -> dict:
    """Generic table. A cell may be a value or {"bar":[w,d,l]} for a W/D/L bar."""
    return {"type": "table", "columns": columns, "rows": rows}


def wdl_table(label_col: str, rows: list[dict]) -> dict:
    """rows: [{"label":.., "win":n, "draw":n, "loss":n}] (already sorted/limited)."""
    return {"type": "wdl_table", "label_col": label_col, "rows": rows}


def line(series: list[dict], y_label: str = "", x_label: str = "") -> dict:
    """series: [{"name":.., "points":[y0,y1,..] or [{"x":..,"y":..}]}]."""
    return {"type": "line", "series": series, "y_label": y_label, "x_label": x_label}


def evalbar(plies: list[dict], moves: list[str]) -> dict:
    """Per-ply engine evaluation graph.

    plies: [{"ply":i, "cp":<white-pov centipawns, clamped>}]
    moves: SAN list aligned to plies (for hover labels).
    """
    return {"type": "eval", "plies": plies, "moves": moves}


def board(fen: str, caption: str = "", lastmove: str | None = None,
          svg: str | None = None) -> dict:
    """A single position. `svg` is optional pre-rendered SVG (server-side)."""
    return {"type": "board", "fen": fen, "caption": caption,
            "lastmove": lastmove, "svg": svg}


def group(title: str, widgets: list[dict], layout: str = "row") -> dict:
    """A container that lays out child widgets in a row or grid."""
    return {"type": "group", "title": title, "layout": layout, "widgets": widgets}


def text(body: str) -> dict:
    return {"type": "text", "body": body}
