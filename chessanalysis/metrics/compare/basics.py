"""Comparison metrics (scope="compare"): two players side by side."""
from ...registry import metric
from ... import widgets as W
from ...util import WDL


def _record(games):
    rec = WDL()
    for g in games:
        rec.add(g.outcome)
    return rec


@metric("compare", title=None, order=10)
def headline(ctx):
    ra, rb = _record(ctx.a.games), _record(ctx.b.games)
    ea = [g.user_elo for g in ctx.a.games if g.user_elo]
    eb = [g.user_elo for g in ctx.b.games if g.user_elo]
    return W.cards([
        W.card(f"{100*ra.winrate:.0f}%", "Win rate", sub=ctx.a.player),
        W.card(f"{100*rb.winrate:.0f}%", "Win rate", sub=ctx.b.player),
        W.card(max(ea) if ea else "—", "Peak Elo", sub=ctx.a.player),
        W.card(max(eb) if eb else "—", "Peak Elo", sub=ctx.b.player),
    ])


@metric("compare", title="Records", order=20)
def records(ctx):
    rows = []
    for pc in (ctx.a, ctx.b):
        r = _record(pc.games)
        rows.append({"label": pc.player, "win": r.win, "draw": r.draw, "loss": r.loss})
    return W.wdl_table("Player", rows)


@metric("compare", title="Head to head", order=30)
def head_to_head(ctx):
    if not ctx.head_to_head:
        return W.text(f"No games found between {ctx.a.player} and {ctx.b.player}.")
    r = _record(ctx.head_to_head)
    return W.wdl_table("From " + ctx.a.player + "'s side",
                       [{"label": "vs " + ctx.b.player,
                         "win": r.win, "draw": r.draw, "loss": r.loss}])
