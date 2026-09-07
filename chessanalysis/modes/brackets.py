"""Brackets mode: the rating corpus, at two scopes.

The same statistics answer both questions people actually ask — "how do I
compare with people at my rating" and "what changes as rating goes up" — so
they are one tab with a scope switch rather than two tabs of near-identical
tables.

    scope="peers"   you against your own band, measured in the same currency
    scope="ladder"  every band, side by side
"""
from __future__ import annotations

from . import mode, run_metrics
from .. import corpus
from ..contexts import CohortContext
from ..document import Document


@mode("brackets")
def brackets(username: str = "", scope: str = "ladder", window: int = 70,
             depth: int | None = None) -> Document:
    depth = depth or corpus.DEPTH
    t = corpus.totals(depth)
    ctx = CohortContext(user=username, depth=depth, scope=scope, totals=t)

    if scope == "peers":
        from ..model import load_games

        ctx.me = corpus.mine(username, depth)
        if not ctx.me:
            raise SystemExit(f"No analysed games for '{username}' yet.")
        games = [g for g in load_games(username) if g.user_elo]
        my_elo = games[-1].user_elo if games else 1500
        ctx.lo, ctx.hi = my_elo - window, my_elo + window
        ctx.band = my_elo // corpus.BAND_SIZE * corpus.BAND_SIZE
        ctx.cohort = corpus.cohort(ctx.lo, ctx.hi, depth)
        if not ctx.cohort:
            raise SystemExit(f"The corpus holds no games at {ctx.lo}-{ctx.hi} yet "
                             "— use Expand database.")
        ctx.hist = corpus.accuracy_histogram(ctx.lo, ctx.hi, depth)
        ctx.percentile = corpus.percentile(ctx.me["acc"], ctx.lo, ctx.hi, depth)
        title = f"{username} vs peers"
        sub = (f"{my_elo} ± {window} · {int(ctx.cohort['n'])} peer games vs "
               f"{int(ctx.me['n'])} of yours · depth {depth}")
    else:
        ctx.bands = corpus.ladder(depth)
        if not ctx.bands:
            raise SystemExit("The corpus is empty — use Expand database to fill it.")
        ctx.me = corpus.mine(username, depth) if username else None
        title = "Rating brackets"
        sub = (f"{t['games']} games from {t['players']} players · "
               f"{t['samples']} samples · depth {depth}")

    doc = Document(mode="brackets", title=title, subtitle=sub,
                   meta={"scope": scope, "depth": depth, **t})
    run_metrics("brackets", ctx, doc)
    return doc
