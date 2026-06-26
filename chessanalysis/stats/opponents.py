"""Most-played opponents."""
from collections import Counter

from ..registry import register
from ..render import table, esc


@register("Most-played opponents", order=50)
def opponents(games):
    counts = Counter(g.opponent for g in games)
    rows = [[esc(o), n] for o, n in counts.most_common(10)]
    return table(["Opponent", "Games"], rows)
