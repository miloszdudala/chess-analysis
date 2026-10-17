"""Game review mode: deep engine analysis of a single game."""
from __future__ import annotations

from . import mode, run_metrics
from ..contexts import GameContext
from ..document import Document
from ..enrich import engine
from ..model import load_games


def _select(games, selector):
    """Resolve a selector to one game: game_id, opponent name, or index."""
    if selector in (None, "last", "-1"):
        return games[-1]
    for g in games:                      # exact game id
        if g.game_id == selector:
            return g
    if selector.lstrip("-").isdigit() and abs(int(selector)) < len(games):
        return games[int(selector)]      # index into the chronological list
    matches = [g for g in games if selector.lower() in g.opponent.lower()]
    if matches:
        return matches[-1]               # most recent vs that opponent
    raise SystemExit(f"No game '{selector}' among this account's games.")


@mode("game")
def game_review(username: str, selector=None, depth=None) -> Document:
    games = load_games(username, include_flagged=True)
    if not games:
        raise SystemExit(f"No games stored for '{username}'.")
    game = _select(games, selector)

    analysis = engine.analyse_game(game, depth=depth)
    ctx = GameContext(game=game, analysis=analysis, player=username)

    opp = game.opponent
    doc = Document(
        mode="game",
        title=f"{game.h('White')} vs {game.h('Black')}",
        subtitle=f"{game.h('Result')} · {game.time_class} · {game.date} · "
                 f"vs {opp} · engine depth {analysis.depth}",
        meta={"game_id": game.game_id, "player": username,
              "url": game.h("Link"), "depth": analysis.depth},
    )
    run_metrics("game", ctx, doc)
    return doc
