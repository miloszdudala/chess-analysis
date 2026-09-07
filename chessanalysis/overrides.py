"""User overrides for the auto-diagnosis — manually corrected win/loss reasons
and games flagged as not representative.

The heuristic in `diagnosis` is occasionally wrong; a player can correct the
reason flag for a game in its review. Corrections are stored here (one small
JSON file) and applied everywhere the diagnosis is used: the single-game
verdict and the aggregate "why you win & lose" distribution.

The same file holds *game flags*: a game whose result says nothing about how
either player played (an opponent's disconnect, a deliberately thrown game).
Flagged games are dropped from every statistic — `model.load_games` filters
them out by default — but stay reviewable and stay listed in the history, so
flagging is a way to annotate the record rather than to hide it.
"""
from __future__ import annotations

import json
import os
import threading

_PATH = os.path.join("data", "overrides.json")
_LOCK = threading.Lock()

# the one flag: this result says nothing about how anyone played — a
# disconnect, a game thrown on purpose, an opening tried for fun
ANOMALY = "anomaly"
FLAGS = {ANOMALY: "Anomalous — doesn't count toward stats"}


def _load_all() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _update(game_id, **fields) -> None:
    """Merge `fields` into one game's entry; None clears a field, and an entry
    with nothing left in it is dropped so the file stays small."""
    with _LOCK:
        data = _load_all()
        gid = str(game_id)
        entry = dict(data.get(gid) or {})
        for k, v in fields.items():
            if v is None:
                entry.pop(k, None)
            else:
                entry[k] = v
        if entry:
            data[gid] = entry
        else:
            data.pop(gid, None)
        _write(data)


def get(game_id) -> dict | None:
    """The override entry for one game, e.g. {"primary": "blunder"}, or None."""
    if not game_id:
        return None
    return _load_all().get(str(game_id))


def set_reason(game_id, primary: str | None) -> None:
    """Set (or, with primary=None, clear) the manual reason for a game."""
    _update(game_id, primary=primary)


def set_flag(game_id, flag: str | None, note: str | None = None) -> None:
    """Flag a game as not representative (or, with flag=None, unflag it).

    `note` is the player's own words for what happened; it is cleared along
    with the flag so a stale note can't outlive the reason it was written for.
    """
    if flag is None:
        _update(game_id, flag=None, note=None)
    else:
        _update(game_id, flag=flag, note=note or None)


def get_flag(game_id) -> dict | None:
    """{"flag": key, "note": str|None} for a flagged game, else None."""
    entry = get(game_id) or {}
    if entry.get("flag") not in FLAGS:
        return None
    return {"flag": entry["flag"], "note": entry.get("note")}


def flags() -> dict[str, dict]:
    """{game_id: {"flag":.., "note":..}} for every flagged game — one read, for
    callers annotating a whole list of games."""
    return {gid: {"flag": e["flag"], "note": e.get("note")}
            for gid, e in _load_all().items()
            if isinstance(e, dict) and e.get("flag") in FLAGS}


def flagged_ids() -> set[str]:
    """Every flagged game id — the set excluded from statistics."""
    return set(flags())
