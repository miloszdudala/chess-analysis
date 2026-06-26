"""Categorical W/D/L breakdowns — each is a one-liner over tally()."""
from collections import Counter

from ...registry import metric
from ... import widgets as W
from ...util import tally, wdl_rows


@metric("player", title="By color", order=20)
def by_color(ctx):
    return W.wdl_table("Color", wdl_rows(tally(ctx.games, lambda g: g.color.title())))


@metric("player", title="By time control", order=30)
def by_time_control(ctx):
    return W.wdl_table("Format", wdl_rows(tally(ctx.games, lambda g: g.time_class)))


@metric("player", title="Top openings", order=40)
def top_openings(ctx):
    return W.wdl_table("Opening",
                       wdl_rows(tally(ctx.games, lambda g: g.opening), limit=15))


@metric("player", title="Most-played opponents", order=50)
def opponents(ctx):
    counts = Counter(g.opponent for g in ctx.games)
    rows = [[o, n] for o, n in counts.most_common(10)]
    return W.table(["Opponent", "Games"], rows)
