"""Your record against each country your opponents play for.

The country is the one on the opponent's Chess.com profile, cached by the
profile lookup a sync already makes (see `fairplay`), so this never touches
the network. Chess.com also offers regions as countries — England, Catalonia —
and `MAP` folds those onto the country whose shape they sit in on the map.
"""
from __future__ import annotations

from . import fairplay

# Chess.com's own codes: (name, the map shape it is drawn in, or None).
REGIONS = {
    "XE": ("England", "GB"), "XS": ("Scotland", "GB"), "XW": ("Wales", "GB"),
    "XI": ("Northern Ireland", "GB"), "XB": ("Basque Country", "ES"),
    "XC": ("Catalonia", "ES"), "XG": ("Galicia", "ES"), "XA": ("Canary Islands", "ES"),
    "XP": ("Palestine", "PS"), "XX": ("International", None), "EU": ("European Union", None),
}


def record(games) -> dict:
    """{"countries": [...], "unknown": n, "total": n}, most-played first.

    Each country is {"code", "name", "map", "games", "win", "draw", "loss",
    "score"}; `name` is set only for Chess.com's own codes (the page names the
    rest from its map), `map` is the shape to colour, and `score` is your
    score against them as a fraction (a draw is half)."""
    rows: dict[str, dict] = {}
    unknown = 0
    for g in games:
        if g.outcome not in ("win", "draw", "loss"):
            continue
        code = fairplay.country(g.opponent) if g.opponent else None
        if not code:
            unknown += 1
            continue
        name, shape = REGIONS.get(code, (None, code))
        row = rows.setdefault(code, {"code": code, "name": name, "map": shape,
                                     "games": 0, "win": 0, "draw": 0, "loss": 0})
        row["games"] += 1
        row[g.outcome] += 1
    for row in rows.values():
        row["score"] = round((row["win"] + row["draw"] / 2) / row["games"], 3)
    countries = sorted(rows.values(), key=lambda r: (-r["games"], r["code"]))
    return {"countries": countries, "unknown": unknown,
            "total": unknown + sum(r["games"] for r in countries)}
