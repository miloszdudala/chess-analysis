"""User overrides for the auto-diagnosis — manually corrected win/loss reasons.

The heuristic in `diagnosis` is occasionally wrong; a player can correct the
reason flag for a game in its review. Corrections are stored here (one small
JSON file) and applied everywhere the diagnosis is used: the single-game
verdict and the aggregate "why you win & lose" distribution.
"""
from __future__ import annotations

import json
import os
import threading

_PATH = os.path.join("data", "overrides.json")
_LOCK = threading.Lock()


def _load_all() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def get(game_id) -> dict | None:
    """The override for one game, e.g. {"primary": "blunder"}, or None."""
    if not game_id:
        return None
    return _load_all().get(str(game_id))


def set_reason(game_id, primary: str | None) -> None:
    """Set (or, with primary=None, clear) the manual reason for a game."""
    with _LOCK:
        data = _load_all()
        if primary is None:
            data.pop(str(game_id), None)
        else:
            data[str(game_id)] = {"primary": primary}
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
