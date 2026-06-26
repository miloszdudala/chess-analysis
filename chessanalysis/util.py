"""Aggregation helpers so new stats are usually a one-liner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .model import Game


@dataclass
class WDL:
    """Win/draw/loss tally for a group of games."""
    win: int = 0
    draw: int = 0
    loss: int = 0

    def add(self, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)

    @property
    def total(self) -> int:
        return self.win + self.draw + self.loss

    @property
    def score(self) -> float:
        """Points-style score (win=1, draw=0.5) as a fraction, 0..1."""
        return (self.win + 0.5 * self.draw) / self.total if self.total else 0.0

    @property
    def winrate(self) -> float:
        return self.win / self.total if self.total else 0.0


def tally(games: Iterable[Game], key: Callable[[Game], object]) -> dict:
    """Group games by key(game) and tally W/D/L. Skips keys that are None."""
    out: dict = {}
    for g in games:
        k = key(g)
        if k is None:
            continue
        out.setdefault(k, WDL()).add(g.outcome)
    return out
