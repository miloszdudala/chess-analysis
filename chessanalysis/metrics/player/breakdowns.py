"""Results: W/D/L split by colour."""
from ...registry import metric
from ... import widgets as W
from ...util import tally, wdl_rows

CAT = "Results & form"


@metric("player", title="By color", order=20, category=CAT)
def by_color(ctx):
    return W.wdl_barstack(wdl_rows(tally(ctx.games, lambda g: g.color.title())))
