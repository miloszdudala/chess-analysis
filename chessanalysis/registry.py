"""Stat registry. Stats self-register via @register and are run in order."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .model import Game

# A stat takes the bound games and returns an HTML body string (or "" to skip).
StatFn = Callable[[list[Game]], str]


@dataclass
class Stat:
    order: int
    title: str | None   # rendered as a section heading; None = no heading
    fn: StatFn


_REGISTRY: list[Stat] = []


def register(title: str | None = None, order: int = 100):
    """Decorator: register a stat block.

    @register("By color", order=20)
    def by_color(games): ...
    """
    def deco(fn: StatFn) -> StatFn:
        _REGISTRY.append(Stat(order=order, title=title, fn=fn))
        return fn
    return deco


def all_stats() -> list[Stat]:
    return sorted(_REGISTRY, key=lambda s: (s.order, s.title or ""))
