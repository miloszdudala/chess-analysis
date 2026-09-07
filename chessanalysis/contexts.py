"""Per-mode context objects — the input shape each metric scope receives.

Each mode builds one of these and passes it to its metrics. New mode = new
context type + a mode file; existing metrics of that scope are reused as-is.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Game


@dataclass
class PlayerContext:
    """scope="player" — one player's games (perspective-bound)."""
    player: str
    games: list[Game]


@dataclass
class GameContext:
    """scope="game" — a single game plus its engine analysis (may be None)."""
    game: Game
    analysis: "object" = None   # enrich.engine.GameAnalysis
    player: str = ""            # which side to highlight, if known


@dataclass
class CompareContext:
    """scope="compare" — two player cohorts and their head-to-head games."""
    a: PlayerContext
    b: PlayerContext
    head_to_head: list[Game] = field(default_factory=list)


@dataclass
class CohortContext:
    """scope="peers" / "brackets" — the rating corpus, aggregated.

    Metrics get finished aggregates rather than games: a bracket statistic is a
    SQL sum over millions of moves, and materialising them would defeat the
    point of storing the corpus outside memory.
    """
    user: str
    depth: int
    lo: int = 0                     # peers: the rating window compared against
    hi: int = 0
    band: int | None = None         # peers: the band you sit in
    me: dict | None = None          # your aggregate, same engine + depth
    cohort: dict | None = None      # the cohort's aggregate
    bands: list = field(default_factory=list)      # brackets: the ladder
    hist: list = field(default_factory=list)       # peers: accuracy distribution
    percentile: int | None = None
    totals: dict = field(default_factory=dict)
