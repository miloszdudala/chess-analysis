"""Player report mode: one player's games, optionally filtered to one format.

Mixed-format stats are misleading (a bullet blunder rate vs a rapid one), so the
web app gates the report on a chosen time class. `time_class=None` keeps all
games (used by the CLI for a quick overview).
"""
from __future__ import annotations

from . import mode, run_metrics
from ..contexts import PlayerContext
from ..document import Document
from ..model import load_games


@mode("player")
def player_report(username: str, time_class: str | None = None) -> Document:
    games = load_games(username)
    if not games:
        raise SystemExit(
            f"No games stored for '{username}'. Run scraper.py first."
        )
    if time_class:
        games = [g for g in games if g.time_class == time_class]
        if not games:
            raise SystemExit(f"No {time_class} games for '{username}'.")

    ctx = PlayerContext(player=username, games=games)
    fmt = time_class.title() if time_class else "All formats"
    doc = Document(
        mode="player",
        title=username,
        subtitle=f"{fmt} · {len(games)} games",
        meta={"player": username, "games": len(games), "format": time_class},
    )
    run_metrics("player", ctx, doc)
    return doc
