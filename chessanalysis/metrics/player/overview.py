"""Headline cards + rating trend (with per-point date for the chart tooltip)."""
from ...registry import metric
from ... import widgets as W
from ...util import WDL


@metric("player", title="Summary", order=10, category="Overview")
def summary(ctx):
    rec = WDL()
    for g in ctx.games:
        rec.add(g.outcome)
    elos = [g.user_elo for g in ctx.games if g.user_elo]
    pct = f"{100 * rec.winrate:.0f}%" if rec.total else "—"
    return W.cards([
        W.card(rec.win, "Wins"),
        W.card(rec.draw, "Draws"),
        W.card(rec.loss, "Losses"),
        W.card(pct, "Win rate"),
        W.card(elos[-1] if elos else "—", "Latest Elo"),
        W.card(max(elos) if elos else "—", "Peak Elo"),
    ])


@metric("player", title="Rating", order=15, category="Overview")
def rating_trend(ctx):
    pts = [{"x": g.date, "y": g.user_elo}
           for g in ctx.games if g.user_elo]
    if len(pts) < 2:
        return None
    return W.line([{"name": ctx.player, "points": pts}], y_label="Elo")
