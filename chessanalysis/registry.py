"""Metric registry. Metrics self-register via @metric, tagged by `scope`.

A metric is compute-only: it takes a Context and returns widget data
(a dict, or a list of dicts), never HTML. Modes collect the metrics whose
scope matches and assemble them into a Document.

    @metric("player", "By color", order=20)
    def by_color(ctx): return wdl_table(...)

Scopes correspond to modes:
    "player"  -> one player's games   (PlayerContext)
    "game"    -> one game + engine     (GameContext)
    "compare" -> two players           (CompareContext)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# A metric returns a widget dict or a list of widget dicts (or "" / None to skip).
MetricFn = Callable[[object], object]


@dataclass
class Metric:
    scope: str
    title: str | None         # section heading; None = render headingless
    order: int
    fn: MetricFn
    needs: tuple = ()          # capability hints, e.g. ("engine",) — for docs/validation
    category: str | None = None   # groups sections in the UI (e.g. "Openings")
    id: str = ""


_REGISTRY: list[Metric] = []


def metric(scope: str, title: str | None = None, order: int = 100,
           needs=(), category: str | None = None):
    def deco(fn: MetricFn) -> MetricFn:
        _REGISTRY.append(Metric(
            scope=scope, title=title, order=order, fn=fn,
            needs=tuple(needs), category=category, id=fn.__name__,
        ))
        return fn
    return deco


def metrics_for(scope: str) -> list[Metric]:
    return sorted(
        (m for m in _REGISTRY if m.scope == scope),
        key=lambda m: (m.order, m.title or ""),
    )
