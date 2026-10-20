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
from .. import corpus, weaknesses
from ..contexts import CohortContext
from ..document import Document


# How many cohort games the reused player-report stats run over. They hold a
# full per-move analysis each, which is the only part of this page that costs
# real memory, so the cohort is sampled rather than loaded whole.
REUSE_LIMIT = 400


def _no_drilldown(widgets):
    """Strip the per-game lists out of reused widgets.

    The player report lets you click a reason and open the games behind it.
    Here a reason covers hundreds of strangers' games, so the list is noise —
    and the rows carry ids that belong to no account on this page.
    """
    out = []
    for w in widgets:
        if w.get("type") == "reasons":
            w = {**w, "groups": [{**g, "games": []} for g in w["groups"]]}
        elif w.get("type") == "drilltable":
            w = {**w, "rows": [{**r, "games": []} for r in w["rows"]]}
        elif w.get("type") == "text":
            w = {**w, "body": w["body"].replace(
                " Click any reason to see the games behind it.", "")}
        out.append(w)
    return out


def _depersonalise(widgets):
    """Reword a reused section that now describes a population, not a person.

    The player report addresses you directly, which is right there and wrong
    here: these rows are hundreds of different players' habits.
    """
    swap = [("You play", "Move played"), ("Your score (W-D-L)", "Score (W-D-L)"),
            ("Exact positions you reached", "Positions reached"),
            ("answered with the same move", "answered with the same move by "
             "different players"),
            (" Click a row to open the games behind it.", ""),
            ("your repertoire", "the corpus"), ("repertoire habits", "shared habits")]
    out = []
    for w in widgets:
        w = dict(w)
        if "columns" in w:
            w["columns"] = [next((b for a, b in swap if a == c), c) for c in w["columns"]]
        if w.get("type") == "text":
            for a, b in swap:
                w["body"] = w["body"].replace(a, b)
        out.append(w)
    return out


@mode("brackets")
def brackets(username: str = "", scope: str = "ladder", window: int = 70,
             depth: int | None = None) -> Document:
    depth = depth or corpus.DEPTH
    t = corpus.totals(depth)
    ctx = CohortContext(user=username, depth=depth, scope=scope, totals=t)

    if scope == "peers":
        from ..model import load_games
        from ..corpus import analyse as corpus_analyse

        # games played since the last visit have no corpus-depth analysis yet,
        # and would otherwise be silently missing from every number below
        corpus_analyse.analyse_own(username, depth)
        ctx.me = corpus.mine(username, depth)
        if not ctx.me:
            raise SystemExit(f"No analysed games for '{username}' yet.")
        games = [g for g in load_games(username) if g.user_elo]
        my_elo = games[-1].user_elo if games else 1500
        ctx.lo, ctx.hi = my_elo - window, my_elo + window
        ctx.band = my_elo // corpus.BAND_SIZE * corpus.BAND_SIZE
        ctx.cohort = corpus.cohort(ctx.lo, ctx.hi, depth)
        if not ctx.cohort:
            raise SystemExit(f"There are no other players' games rated {ctx.lo}–{ctx.hi} "
                             "yet — use Expand the corpus.")
        ctx.percentile = corpus.player_percentile(ctx.me["acc"], ctx.lo,
                                                  ctx.hi, depth)
        ctx.who = f"players rated {ctx.lo}–{ctx.hi}"
        title = f"{username} against players at your rating"
        sub = (f"Your {int(ctx.me['n'])} games against {int(ctx.cohort['n'])} game "
               f"sides of {ctx.who} (your rating {my_elo} ± {window}) · same engine, "
               f"depth {depth}")
    else:
        ctx.bands = corpus.ladder(depth)
        if not ctx.bands:
            raise SystemExit("No other players' games yet — use Expand the corpus.")
        ctx.me = corpus.mine(username, depth) if username else None
        title = "What changes as rating rises"
        sub = (f"{t['games']} games from {t['players']} players, each side counted "
               f"({t['samples']} game sides) · engine depth {depth}")

    doc = Document(mode="brackets", title=title, subtitle=sub,
                   meta={"scope": scope, "depth": depth, **t})
    run_metrics("brackets", ctx, doc)

    if scope == "ladder":
        # Recurring opening mistakes wants a population, not a comparison:
        # across hundreds of players a position answered badly again and again
        # is a habit of the *rating*, which is exactly the ladder's subject.
        # At peers scope the me-vs-band metrics in metrics/brackets/compare.py
        # do the reusing instead, tallying both sides through the report's own
        # classifiers rather than copying its sections unchanged.
        for sec in weaknesses.opening_leaks(corpus.pairs(0, 9999, depth, 400)):
            doc.add("Openings the corpus keeps getting wrong",
                    _depersonalise(_no_drilldown(sec["widgets"])))
    return doc
