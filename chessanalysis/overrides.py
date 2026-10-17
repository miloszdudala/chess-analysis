"""User overrides for the auto-diagnosis — manually corrected win/loss reasons
and games flagged as not representative.

The heuristic in `diagnosis` is occasionally wrong; a player can correct the
reason flag for a game in its review. Corrections live in the store's
`overrides` table and are applied everywhere the diagnosis is used: the
single-game verdict and the aggregate "why you win & lose" distribution.

The same row holds the *game flag*: a game whose result says nothing about how
either player played (an opponent's disconnect, a deliberately thrown game).
Flagged games are dropped from every statistic — `model.load_games` filters
them out by default — but stay reviewable and stay listed in the history, so
flagging is a way to annotate the record rather than to hide it.
"""
from __future__ import annotations

from . import store

# the one flag: this result says nothing about how anyone played — a
# disconnect, a game thrown on purpose, an opening tried for fun
ANOMALY = "anomaly"
FLAGS = {ANOMALY: "Anomalous — doesn't count toward stats"}


def _update(game_id, **fields) -> None:
    """Merge `fields` into one game's row; None clears a field, and a row with
    nothing left in it is dropped."""
    gid = str(game_id)
    conn = store.connect()
    row = conn.execute("SELECT reason, flag, note FROM overrides WHERE gid=?",
                       (gid,)).fetchone()
    entry = dict(row) if row else {"reason": None, "flag": None, "note": None}
    entry.update(fields)
    if any(entry.values()):
        conn.execute("INSERT OR REPLACE INTO overrides(gid,reason,flag,note) "
                     "VALUES(?,?,?,?)", (gid, entry["reason"], entry["flag"],
                                         entry["note"]))
    else:
        conn.execute("DELETE FROM overrides WHERE gid=?", (gid,))
    conn.commit()


def get(game_id) -> dict | None:
    """The override entry for one game, e.g. {"primary": "blunder"}, or None."""
    if not game_id:
        return None
    row = store.connect().execute(
        "SELECT reason, flag, note FROM overrides WHERE gid=?",
        (str(game_id),)).fetchone()
    if row is None:
        return None
    out = {"primary": row["reason"], "flag": row["flag"], "note": row["note"]}
    return {k: v for k, v in out.items() if v is not None} or None


def set_reason(game_id, primary: str | None) -> None:
    """Set (or, with primary=None, clear) the manual reason for a game."""
    _update(game_id, reason=primary)


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
    return {r["gid"]: {"flag": r["flag"], "note": r["note"]}
            for r in store.connect().execute(
                "SELECT gid, flag, note FROM overrides WHERE flag IS NOT NULL")
            if r["flag"] in FLAGS}


def flagged_ids() -> set[str]:
    """Every flagged game id — the set excluded from statistics."""
    return set(flags())
