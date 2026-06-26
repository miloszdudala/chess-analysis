"""Headline cards + rating trend."""
from ...registry import metric
from ... import widgets as W
from ...util import WDL


@metric("player", title=None, order=10)
def overview(ctx):
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


@metric("player", title="Rating trend", order=15)
def rating_trend(ctx):
    elos = [g.user_elo for g in ctx.games if g.user_elo]
    if len(elos) < 2:
        return None
    return W.line([{"name": ctx.player, "points": elos}], y_label="Elo")
