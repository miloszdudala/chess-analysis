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
class ScoutContext:
    """scope="scout" — an opponent's recent games, and yours beside them.

    `games` are theirs, from their point of view; `mine` are the scouting
    player's own games (any colour), so their main lines can be set against
    your experience of the same positions; `head_to_head` are the games
    between the two, from your point of view.
    """
    opponent: str
    games: list[Game]
    me: str = ""
    mine: list[Game] = field(default_factory=list)
    head_to_head: list[Game] = field(default_factory=list)
    time_class: str | None = None
    months: int = 0


@dataclass
class CohortContext:
    """scope="peers" / "brackets" — the rating corpus, aggregated.

    Metrics get finished aggregates rather than games: a bracket statistic is a
    SQL sum over millions of moves, and materialising them would defeat the
    point of storing the corpus outside memory.
    """
    user: str
    depth: int
    scope: str = "ladder"   # "peers" | "ladder"
    lo: int = 0                     # peers: the rating window compared against
    hi: int = 0
    band: int | None = None         # peers: the band you sit in
    me: dict | None = None          # your aggregate, same engine + depth
    cohort: dict | None = None      # the cohort's aggregate
    bands: list = field(default_factory=list)      # brackets: the ladder
    hist: list = field(default_factory=list)       # peers: accuracy distribution
    percentile: int | None = None
    totals: dict = field(default_factory=dict)


@dataclass
class OverviewContext:
    """scope="overview" — the home page: one player, the coach's comparison
    with players at their rating (all games, and recent), and the training
    queue."""
    player: str
    games: list[Game]
    time_class: str | None = None
    coach: dict | None = None          # coach.compare over every counted game
    recent: dict | None = None         # ...over the latest RECENT games
    training: dict | None = None       # training.summary
    pending: int = 0                   # your games not yet analysed for the coach
