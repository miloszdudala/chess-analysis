"""Scout mode: an opponent's recent games, read for preparation.

Their games come from Chess.com like your own, but are stored as source
'scout' so they never enter the rating corpus as a tracked player's would.
"""
from __future__ import annotations

import time

from . import mode, run_metrics
from ..contexts import ScoutContext
from ..document import Document
from ..model import load_games

MONTHS = 6


@mode("scout")
def scout(opponent: str, me: str = "", time_class: str | None = "rapid",
          months: int = MONTHS) -> Document:
    cutoff = time.strftime("%Y.%m.%d", time.gmtime(time.time() - months * 31 * 86400))
    games = [g for g in load_games(opponent) if g.sort_key >= cutoff]
    if time_class:
        games = [g for g in games if g.time_class == time_class]
    mine = load_games(me) if me else []
    if time_class:
        mine = [g for g in mine if g.time_class == time_class]
    h2h = [g for g in mine if g.opponent.lower() == opponent.lower()]
    ctx = ScoutContext(opponent=opponent, games=games, me=me, mine=mine,
                       head_to_head=h2h, time_class=time_class, months=months)
    fmt = time_class.title() if time_class else "All formats"
    doc = Document(mode="scout", title=f"Scouting {opponent}",
                   subtitle=f"{fmt} · {len(games)} games · {len(h2h)} against you",
                   meta={"opponent": opponent, "me": me, "format": time_class})
    run_metrics("scout", ctx, doc)
    return doc
