"""Headline cards: record, win rate, current/peak rating."""
from ..registry import register
from ..render import cards, pct
from ..util import WDL


@register(order=10)  # no title -> rendered without a heading
def overview(games):
    rec = WDL()
    for g in games:
        rec.add(g.outcome)
    elos = [g.user_elo for g in games if g.user_elo]
    return cards([
        (rec.win, "Wins"),
        (rec.draw, "Draws"),
        (rec.loss, "Losses"),
        (pct(rec.win, rec.total), "Win rate"),
        (elos[-1] if elos else "—", "Latest Elo"),
        (max(elos) if elos else "—", "Peak Elo"),
    ])
