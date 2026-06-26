"""Rating trend sparkline (games are pre-sorted chronologically)."""
from ..registry import register
from ..render import sparkline


@register("Rating trend", order=15)
def rating_trend(games):
    elos = [g.user_elo for g in games if g.user_elo]
    return sparkline(elos)
