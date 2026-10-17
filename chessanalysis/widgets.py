"""Widget vocabulary — the backend↔frontend data contract.

Every metric returns one of these JSON-serializable dicts (or a list of them).
The frontend (frontend/js/widgets.js) maps `type` -> view. Adding a chart
type = add a builder here + one renderer there; nothing else changes.

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


def drilltable(columns: list[str], rows: list[dict]) -> dict:
    """A table whose rows expand to reveal the individual games behind them.

    columns: header labels for each row's `cells`.
    rows: [{"cells":[..], "games":[{"id","ply","date","opponent","outcome",
             "note"}]}] — clicking a row toggles its games; clicking a game
    opens that game's review positioned at `ply` (the board at that moment).
    """
    return {"type": "drilltable", "columns": columns, "rows": rows}


def line(series: list[dict], y_label: str = "", x_label: str = "") -> dict:
    """series: [{"name":.., "points":[y0,y1,..] or [{"x":..,"y":..}]}]."""
    return {"type": "line", "series": series, "y_label": y_label, "x_label": x_label}


def xyline(series: list[dict], y_label: str = "", x_label: str = "",
           y_zero: bool = False) -> dict:
    """A plain numeric line chart: x is a number (a rating band), not a date.

    Distinct from `line`, which is the interactive rating chart and assumes a
    dated point per game plus Game/Day/Month grouping — meaningless here.

    series: [{"name":.., "color":?, "points":[{"x":n,"y":n}]}]
    """
    return {"type": "xyline", "series": series, "y_label": y_label,
            "x_label": x_label, "y_zero": y_zero}


def evalbar(plies: list[dict], moves: list[str], me: str = "") -> dict:
    """Per-ply engine evaluation graph.

    plies: [{"ply":i, "cp":<white-pov centipawns, clamped>, "label":..}]
    moves: SAN list aligned to plies (for hover labels).
    me:    the analysed player's colour ("white"/"black") so the UI can filter
           flagged points to "mine" vs "the opponent's".
    """
    return {"type": "eval", "plies": plies, "moves": moves, "me": me}


def evalcurve(groupings: list[dict], default: str = "color",
              y_label: str = "Eval (pawns, your POV)") -> dict:
    """Average-evaluation-by-move chart with switchable groupings.

    groupings: [{"key":.., "label":.., "series":[{"name":.., "color":?,
                 "points":[{"x":<move number>, "y":<pawns>}]}]}].
    The UI shows one button per grouping (e.g. Average / By colour / By result)
    and draws the selected one's centred lines (zero baseline, symmetric range).
    """
    return {"type": "evalcurve", "groupings": groupings, "default": default,
            "y_label": y_label}


def barstack(rows: list[dict], palette: dict, title: str = "") -> dict:
    """Horizontal stacked-bar chart (one bar per row) with a shared legend.

    rows:    [{"label":.., "segments":[{"name":.., "value":n}], "note":?}]
             an optional `note` is shown right-aligned after the bar.
    palette: {segment_name: css_color} — also fixes legend order.
    """
    return {"type": "barstack", "rows": rows, "palette": palette, "title": title}


# shared win/draw/loss colours (match the --win/--draw/--loss CSS variables)
WDL_PALETTE = {"win": "#3f7d5a", "draw": "#cbc3b2", "loss": "#c1573f"}


def wdl_barstack(rows: list[dict], title: str = "") -> dict:
    """W/D/L stacked bars — the visual form of a wdl_table.

    rows: [{"label":.., "win":n, "draw":n, "loss":n}] (same shape wdl_table takes).
    Each bar is annotated with its win-rate and game count.
    """
    bs_rows = []
    for r in rows:
        total = r["win"] + r["draw"] + r["loss"]
        wr = f"{round(100 * r['win'] / total)}%" if total else "—"
        bs_rows.append({
            "label": r["label"],
            "segments": [{"name": "win", "value": r["win"]},
                         {"name": "draw", "value": r["draw"]},
                         {"name": "loss", "value": r["loss"]}],
            "note": f"{wr} · {total}g",
        })
    return {"type": "barstack", "rows": bs_rows, "palette": WDL_PALETTE, "title": title}


def timeline(items: list[dict], title: str = "") -> dict:
    """A chronological strip of result cells (oldest → newest).

    items: [{"outcome":"win"|"draw"|"loss", "label":?, "id":?}] — `label` is
    the tooltip; with an `id` the cell opens that game's review.
    """
    return {"type": "timeline", "items": items, "title": title}


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


def verdict(game_id, label, headline, sub, detail, outcome, primary,
            options, manual=False, anomalous=False, cheated=None) -> dict:
    """The game's win/loss verdict with a manual reason override (web app).

    options: [{"key":.., "label":..}] — the reasons selectable for this outcome.
    `primary` is the current reason key; `manual` flags a user override. The UI
    renders a dropdown that POSTs /api/verdict to change the flag, plus an
    `anomalous` checkbox (POSTs /api/flag) that drops the game from the stats.
    `cheated` is set when the opponent has since been banned for fair play: the
    game is already excluded automatically, so the UI says so instead of
    leaving the exclusion unexplained.
    """
    return {"type": "verdict", "game_id": game_id, "label": label,
            "headline": headline, "sub": sub, "detail": detail,
            "outcome": outcome, "primary": primary, "options": options,
            "manual": manual, "anomalous": anomalous, "cheated": cheated}


def conversion() -> dict:
    """Placeholder for conversion/stage analysis — fetched lazily (engine-backed)
    via /api/insights over all games of the chosen format."""
    return {"type": "conversion"}


def reasons(label: str, groups: list[dict]) -> dict:
    """Expandable list of outcome reasons, each drilling down to its games.

    groups: [{"label":.., "count":n, "sub":.., "stat":.., "games":[{
                "id","date","opponent","opp_elo","outcome","detail"}]}]
    (pre-sorted by count). Clicking a game row opens that game's review.
    """
    return {"type": "reasons", "label": label, "groups": groups}


def text(body: str) -> dict:
    return {"type": "text", "body": body}


def actions(items: list[dict]) -> dict:
    """A row of buttons that navigate within the app.

    items: [{"label":.., "route": "#/train?kind=missed"}] — `route` is an app
    route (the hash the frontend router reads), never an external URL.
    """
    return {"type": "actions", "items": items}


def gapchart(rows: list[dict], unit: str = "%", note: str = "") -> dict:
    """You against a baseline, one row per measure, as a gap with its interval.

    rows: [{"label":.., "group":.., "gap": x, "lo": x, "hi": x,
            "verdict": "leak"|"strength"|"level", "detail": "..."}]
    Gaps are fractions when unit == "%" (0.12 = 12% more than the baseline).
    Positive is worse — more lost than the baseline.
    """
    return {"type": "gapchart", "rows": rows, "unit": unit, "note": note}


def focus(items: list[dict]) -> dict:
    """Short findings, each with an optional next step.

    items: [{"tone": "leak"|"strength"|"lean"|"info", "title":.., "body":..,
             "action": {"label":.., "route":..} | None}]
    """
    return {"type": "focus", "items": items}
