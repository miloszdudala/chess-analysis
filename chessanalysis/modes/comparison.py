"""Comparison mode: two players side by side.

Scaffolding — the architecture is ready (CompareContext + scope="compare"
metrics). Add metric files under metrics/compare/ to flesh it out.
"""
from __future__ import annotations

from . import mode, run_metrics
from ..contexts import CompareContext, PlayerContext
from ..document import Document
from ..model import load_games


@mode("compare")
def comparison(player_a: str, player_b: str, games_dir: str = "games") -> Document:
    a = PlayerContext(player_a, load_games(games_dir, player_a))
    b = PlayerContext(player_b, load_games(games_dir, player_b))
    head_to_head = [g for g in a.games
                    if g.opponent.lower() == player_b.lower()]
    ctx = CompareContext(a=a, b=b, head_to_head=head_to_head)
    doc = Document(
        mode="compare",
        title=f"{player_a} vs {player_b}",
        subtitle=f"{len(a.games)} vs {len(b.games)} games · "
                 f"{len(head_to_head)} head-to-head",
        meta={"a": player_a, "b": player_b},
    )
    run_metrics("compare", ctx, doc)
    return doc
