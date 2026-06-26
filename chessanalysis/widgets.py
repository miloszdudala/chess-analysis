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


def barstack(rows: list[dict], palette: dict, title: str = "") -> dict:
    """Horizontal stacked-bar chart (one bar per row) with a shared legend.

    rows:    [{"label":.., "segments":[{"name":.., "value":n}]}]
    palette: {segment_name: css_color} — also fixes legend order.
    """
    return {"type": "barstack", "rows": rows, "palette": palette, "title": title}


def board(fen: str, caption: str = "", lastmove: str | None = None,
          svg: str | None = None) -> dict:
    """A single position. `svg` is optional pre-rendered SVG (server-side)."""
    return {"type": "board", "fen": fen, "caption": caption,
            "lastmove": lastmove, "svg": svg}


def review(positions: list[dict], moves: list[dict], orientation: str,
           white: str, black: str) -> dict:
    """Interactive move-by-move board explorer (web app only).

    positions: per-position [{"fen":.., "cp":<white-pov>, "best":[{"uci","san","cp"}]}]
               (len = plies + 1; `best` = engine's top moves at that position)
    moves:     per-move [{"san","uci","label","cp_loss","wp_loss","best_san"}]
    orientation: "white" | "black" — which way to face the board.
    """
    return {"type": "review", "positions": positions, "moves": moves,
            "orientation": orientation, "white": white, "black": black}


def ranking(title: str, rows: list[dict]) -> dict:
    """A ranked list. rows: [{"label":.., "value":.., "sub":?}] (pre-sorted)."""
    return {"type": "ranking", "title": title, "rows": rows}


def movetree(children: list[dict]) -> dict:
    """An expandable opening tree.

    children: list of nodes, each
        {"move":san, "count":n, "w":n,"d":n,"l":n, "mine":bool, "children":[...]}
    sorted by count. `mine` flags moves the analysed player made (vs opponent's).
    """
    return {"type": "movetree", "children": children}


def recent() -> dict:
    """Placeholder for the recent-games list — the web app fetches & analyses
    it lazily (engine-backed) via /api/recent with a 5/10/20/All selector."""
    return {"type": "recent"}


def conversion() -> dict:
    """Placeholder for conversion/stage analysis — fetched lazily (engine-backed)
    via /api/conversion over all games of the chosen format."""
    return {"type": "conversion"}


def group(title: str, widgets: list[dict], layout: str = "row") -> dict:
    """A container that lays out child widgets in a row or grid."""
    return {"type": "group", "title": title, "layout": layout, "widgets": widgets}


def text(body: str) -> dict:
    return {"type": "text", "body": body}
