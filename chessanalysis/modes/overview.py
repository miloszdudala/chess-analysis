"""Overview mode: the home page — where you stand, and what to work on."""
from __future__ import annotations

from . import mode, run_metrics
from .. import coach, corpus, store, training
from ..corpus import analyse as corpus_analyse
from ..contexts import OverviewContext
from ..document import Document
from ..model import load_games

RECENT = 30


@mode("overview")
def overview(username: str, time_class: str | None = "rapid") -> Document:
    games = load_games(username)
    if not games:
        raise SystemExit(f"No games stored for '{username}' yet.")
    if time_class:
        games = [g for g in games if g.time_class == time_class]
    ctx = OverviewContext(player=username, games=games, time_class=time_class)
    corpus_analyse.ensure_samples(corpus.DEPTH)
    at_tc = [g for g in games if g.time_control == corpus.TIME_CONTROL]
    ctx.pending = sum(1 for g in at_tc if not store.has_analysis(g.game_id, corpus.DEPTH))
    # the corpus is 10-minute rapid: only that format has peers to compare with
    if time_class in (None, "rapid"):
        ctx.coach = coach.compare(username)
        if ctx.coach and ctx.coach["games"] > RECENT + 10:
            ctx.recent = coach.compare(username, last=RECENT)
    ctx.training = training.summary(username)
    fmt = time_class.title() if time_class else "All formats"
    doc = Document(mode="overview", title=username,
                   subtitle=f"{fmt} · {len(games)} games counted",
                   meta={"player": username, "format": time_class})
    run_metrics("overview", ctx, doc)
    return doc
