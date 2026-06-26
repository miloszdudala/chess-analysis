"""Categorical W/D/L breakdowns within the chosen format."""
from ...registry import metric
from ... import widgets as W
from ...util import tally, wdl_rows


@metric("player", title="By color", order=20)
def by_color(ctx):
    return W.wdl_table("Color", wdl_rows(tally(ctx.games, lambda g: g.color.title())))
