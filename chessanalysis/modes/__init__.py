"""Mode registry + auto-discovery.

A mode builds a Document for a given scope. Register with @mode("name").
Drop a new file here and it's discovered automatically.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Callable

_MODES: dict = {}


def mode(name: str):
    def deco(fn: Callable):
        _MODES[name] = fn
        return fn
    return deco


def run_metrics(scope: str, ctx, doc) -> None:
    """Run every registered metric for `scope` and append its widgets to `doc`."""
    from .. import metrics as _metrics  # noqa: F401  (triggers metric discovery)
    from ..registry import metrics_for
    for m in metrics_for(scope):
        result = m.fn(ctx)
        doc.add(m.title, result, category=m.category)


def get(name: str):
    _discover()
    return _MODES.get(name)


def names() -> list[str]:
    _discover()
    return sorted(_MODES)


_discovered = False


def _discover():
    global _discovered
    if _discovered:
        return
    for m in pkgutil.iter_modules(__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"{__name__}.{m.name}")
    _discovered = True
