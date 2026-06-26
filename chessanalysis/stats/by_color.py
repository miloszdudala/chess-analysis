"""Results split by the color you played."""
from ..registry import register
from ..render import wdl_table
from ..util import tally


@register("By color", order=20)
def by_color(games):
    return wdl_table("Color", tally(games, lambda g: g.color.title()))
