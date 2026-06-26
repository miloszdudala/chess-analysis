"""Results split by time control (bullet / blitz / rapid / ...)."""
from ..registry import register
from ..render import wdl_table
from ..util import tally


@register("By time control", order=30)
def by_time_control(games):
    return wdl_table("Format", tally(games, lambda g: g.time_class))
