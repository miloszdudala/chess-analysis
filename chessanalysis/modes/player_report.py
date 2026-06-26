"""Player report mode: one player's full game history."""
from __future__ import annotations

from . import mode, run_metrics
from ..contexts import PlayerContext
from ..document import Document
from ..model import load_games


@mode("player")
def player_report(username: str, games_dir: str = "games") -> Document:
    games = load_games(games_dir, username)
    if not games:
        raise SystemExit(
            f"No games for '{username}' in '{games_dir}/'. Run scraper.py first."
        )
    ctx = PlayerContext(player=username, games=games)
    doc = Document(
        mode="player",
        title=f"♟ {username}",
        subtitle=f"{len(games)} games analysed",
        meta={"player": username, "games": len(games)},
    )
    run_metrics("player", ctx, doc)
    return doc
