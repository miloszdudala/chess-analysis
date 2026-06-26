"""Top openings by frequency, with win rate."""
from ..registry import register
from ..render import wdl_table
from ..util import tally


@register("Top openings", order=40)
def top_openings(games):
    return wdl_table("Opening", tally(games, lambda g: g.opening), limit=15)
