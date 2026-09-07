"""How games end, and when — at either scope.

`dec_side` is the side the evaluation first crossed ±2.00 for. Comparing it
with the sample's own colour is what separates converting a winning position
from throwing one away, and a comeback from being outplayed. All four are
counted in SQL over stored columns, so this costs nothing at any corpus size.
"""
from ... import widgets as W
from ...corpus import BAND_SIZE
from ...registry import metric

OUTCOME_ORDER = ["win", "draw", "loss"]
DECISION = [("converted", "Converted a winning position", "#3f7d5a"),
            ("comeback", "Won from behind", "#7d9e6b"),
            ("drawn", "Drawn", "#cbc3b2"),
            ("threw", "Threw away a winning position", "#c1573f"),
            ("outplayed", "Outplayed", "#d89a86")]
WHERE = [("dec_op", "Opening (to move 12)", "#8aa4b8"),
         ("dec_mg", "Middlegame (13–32)", "#c1573f"),
         ("dec_eg", "Endgame (33+)", "#3f7d5a")]


def _rows(ctx):
    """(label, aggregate) pairs for whichever scope is active."""
    if ctx.scope == "peers":
        return [("You", ctx.me), ("Your band", ctx.cohort)]
    return [(f"{b['band']}–{b['band'] + BAND_SIZE - 1}", b) for b in ctx.bands]


@metric("brackets", title="Outcomes", order=40)
def outcomes(ctx):
    """Peers scope only.

    Within a single band both sides of every game are counted, so wins and
    losses are the same number by construction and the chart says nothing. It
    is only informative when one row is you and the other is everyone else.
    The draw rate, which does move with rating, is a column of the ladder
    table instead.
    """
    if ctx.scope != "peers":
        return None
    rows = [{"label": label, "win": int(d["wins"]), "draw": int(d["draws"]),
             "loss": int(d["losses"])} for label, d in _rows(ctx) if d]
    return W.wdl_barstack(rows) if rows else None


@metric("brackets", title="How games are decided", order=50)
def decisions(ctx):
    """The four ways a game ends once someone is winning, plus draws.

    Peers scope only, for the same reason as `outcomes`: inside one band
    "converted" and "outplayed" are the two halves of the same games.
    """
    if ctx.scope != "peers":
        return None
    out = []
    for label, d in _rows(ctx):
        if not d:
            continue
        d = dict(d)
        d["drawn"] = int(d["draws"])
        total = sum(int(d[k] or 0) for k, _, _ in DECISION) or 1
        out.append({"label": label,
                    "segments": [{"name": name, "value": int(d[key] or 0)}
                                 for key, name, _ in DECISION],
                    "note": f"{100 * int(d['threw'] or 0) / total:.0f}% thrown"})
    if not out:
        return None
    return [W.text("A game counts as 'winning' once the evaluation crosses "
                   "±2.00. Throwing that away is the one column here you can "
                   "do something about."),
            W.barstack(out, {name: col for _, name, col in DECISION})]


@metric("brackets", title="Where games are decided", order=60)
def where_decided(ctx):
    """The phase in which the eval first crossed ±2.00.

    This one survives at both scopes: it is a property of the games, not of
    who won them, so counting both sides doubles it rather than mirroring it.
    """
    rows, series = [], {name: [] for _, name, _ in WHERE}
    for label, d in _rows(ctx):
        if not d:
            continue
        total = sum(int(d[k] or 0) for k, _, _ in WHERE) or 1
        rows.append({"label": label,
                     "segments": [{"name": name, "value": int(d[key] or 0)}
                                  for key, name, _ in WHERE],
                     "note": f"avg move {d['dec_move']:.0f}" if d["dec_move"] else ""})
        for key, name, _ in WHERE:
            series[name].append(100 * int(d[key] or 0) / total)
    if not rows:
        return None
    widgets = [W.barstack(rows, {name: col for _, name, col in WHERE})]
    if ctx.scope == "ladder":
        widgets.append(W.xyline(
            [{"name": name, "color": col,
              "points": [{"x": b["band"], "y": round(series[name][i], 1)}
                         for i, b in enumerate(ctx.bands)]}
             for _, name, col in WHERE],
            y_label="% of games decided here", x_label="Rating band", y_zero=True))
    return widgets
