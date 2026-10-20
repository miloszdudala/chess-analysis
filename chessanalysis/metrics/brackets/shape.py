"""Corpus-shape statistics that the player report has no equivalent of."""
from ... import widgets as W
from ...corpus import BAND_SIZE
from ...registry import metric

WHERE = [("dec_op", "Opening", "#8aa4b8"),
         ("dec_mg", "Middlegame", "#c1573f"),
         ("dec_eg", "Endgame", "#3f7d5a")]
COLOURS = {"white": "#d9d2c2", "draw": "#cbc3b2", "black": "#4a4a4a"}


def _rows(ctx):
    """(label, aggregate) pairs for whichever scope is active."""
    if ctx.scope == "peers":
        return [("You", ctx.me), (ctx.who[0].upper() + ctx.who[1:], ctx.cohort)]
    return [(f"{b['band']}–{b['band'] + BAND_SIZE - 1}", b) for b in ctx.bands]


@metric("brackets", title="White, draw, black", order=35)
def colour_split(ctx):
    """Counted once per game, unlike everything else here.

    Every other statistic counts both sides of a game, which would make this
    question vacuous: each white win is also a black loss, so the split would
    be 50/50 by construction whatever the data said.
    """
    from ... import corpus

    if ctx.scope != "ladder":
        return None                # a corpus-wide fact, with no "you" side
    split = [s for s in corpus.colour_split(ctx.depth) if s["games"] >= 30]
    if not split:
        return None
    rows = [{"label": f"{s['band']}–{s['band'] + BAND_SIZE - 1}",
             "segments": [{"name": "white", "value": s["white"]},
                          {"name": "draw", "value": s["draw"]},
                          {"name": "black", "value": s["black"]}],
             "note": f"White wins {100 * s['white'] / s['games']:.0f}% · {s['games']} games"}
            for s in split]
    tot = {k: sum(s[k] for s in split) for k in ("white", "draw", "black", "games")}
    rows.append({"label": "All bands",
                 "segments": [{"name": c, "value": tot[c]}
                              for c in ("white", "draw", "black")],
                 "note": f"White wins {100 * tot['white'] / tot['games']:.0f}% · {tot['games']} games"})
    return [W.barstack(rows, COLOURS),
            W.text(f"Each game counted once, in the range of the two players' average "
                   f"rating. Over all {tot['games']} games White scores "
                   f"{100 * (tot['white'] + tot['draw'] / 2) / tot['games']:.1f}% (wins plus "
                   f"half the draws).")]


@metric("brackets", title="Where games are decided", order=60)
def where_decided(ctx):
    """The phase in which the eval first crossed ±2.00.

    Counting both sides doubles this rather than mirroring it — it is a
    property of the game, not of who won — so it is meaningful at either scope.
    """
    if ctx.scope != "ladder":
        return None       # at peers scope this lives as a line in "Where the gap is"
    rows = []
    for label, d in _rows(ctx):
        if not d:
            continue
        total = sum(int(d[k] or 0) for k, _, _ in WHERE) or 1
        rows.append({"label": label,
                     "segments": [{"name": name, "value": int(d[key] or 0)}
                                  for key, name, _ in WHERE],
                     "note": f"on average at move {d['dec_move']:.0f}" if d["dec_move"] else ""})
    if not rows:
        return None
    widgets = [W.text("The phase in which the evaluation first reached ±2.00 — the "
                      "point where one side had a winning advantage."),
               W.barstack(rows, {name: col for _, name, col in WHERE})]
    if ctx.scope == "ladder":
        widgets.append(W.xyline(
            [{"name": name, "color": col,
              "points": [{"x": b["band"],
                          "y": round(100 * int(b[key] or 0)
                                     / max(sum(int(b[k] or 0) for k, _, _ in WHERE), 1), 1)}
                         for b in ctx.bands]}
             for key, name, col in WHERE],
            y_label="% of games decided here", x_label="Rating (start of range)",
            y_zero=True))
    return widgets
