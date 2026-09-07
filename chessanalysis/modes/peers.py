"""Peers mode: you against the players who are actually at your rating.

Your side is re-analysed at the corpus depth rather than read back from a
review-depth analysis. Mixing depths would bias the comparison by roughly half
an accuracy point — the same size as the gap being measured.
"""
from __future__ import annotations

from . import mode, run_metrics
from .. import corpus
from ..contexts import CohortContext
from ..document import Document


@mode("peers")
def peers(username: str, window: int = 70, depth: int | None = None) -> Document:
    depth = depth or corpus.DEPTH
    from ..model import load_games

    me = corpus.mine(username, depth)
    if not me:
        raise SystemExit(f"No analysed games for '{username}' yet.")
    games = [g for g in load_games(username) if g.user_elo]
    my_elo = games[-1].user_elo if games else 1500
    lo, hi = my_elo - window, my_elo + window
    cohort = corpus.cohort(lo, hi, depth)
    if not cohort:
        raise SystemExit(
            f"The corpus holds no games at {lo}-{hi} yet — use Expand database.")
    ctx = CohortContext(
        user=username, depth=depth, lo=lo, hi=hi, band=my_elo // 100 * 100,
        me=me, cohort=cohort, hist=corpus.accuracy_histogram(lo, hi, depth),
        percentile=corpus.percentile(me["acc"], lo, hi, depth),
        totals=corpus.totals(depth))
    doc = Document(
        mode="peers", title=f"{username} vs peers",
        subtitle=f"{my_elo} ± {window} · {int(cohort['n'])} peer games vs "
                 f"{int(me['n'])} of yours · depth {depth}",
        meta={"player": username, "elo": my_elo, "lo": lo, "hi": hi, "depth": depth})
    run_metrics("peers", ctx, doc)
    return doc
