"""The game history as rows: every game, with what is already known about it.

Built from stored analyses only — listing games never starts the engine. A
game without an analysis yet shows its result and opening; the background
pre-warm fills in the rest, and the next listing picks it up.
"""
from __future__ import annotations

import threading

from . import book, config, diagnosis as dx, fairplay, overrides, store
from .enrich import engine as eng
from .model import load_games

_LOCK = threading.Lock()
_MEMO: dict = {}          # (gid, depth) -> summary of that analysis


def _summary(g, depth):
    key = (str(g.game_id), depth)
    with _LOCK:
        if key in _MEMO:
            return _MEMO[key]
    raw = store.load_analysis(g.game_id, depth)
    out = None
    if raw and raw.get("evals") and raw.get("moves_san"):
        a = eng._derive(raw, depth, raw.get("engine_name", "cache"))
        cp = int(config.get("DECISIVE_CP", "200"))
        dg = dx.diagnose(g, a, cp)
        out = {"accuracy": a.accuracy.get(g.color),
               "opp_accuracy": a.accuracy.get("black" if g.color == "white" else "white"),
               "blunders": a.counts[g.color]["blunder"],
               "reason": dg.primary if dg else None,
               "depth": depth}
    with _LOCK:
        _MEMO[key] = out
    return out


def rows(user: str, time_class: str | None = None) -> list[dict]:
    """Every game, newest first, flagged ones included and marked."""
    games = load_games(user, include_flagged=True)
    if time_class:
        games = [g for g in games if g.time_class == time_class]
    flags = {**overrides.flags(), **fairplay.flags(games)}
    trained = {}
    for r in store.connect().execute(
            "SELECT gid, COUNT(*) n FROM puzzles WHERE user=? AND retired=0 "
            "AND kind<>'opening' GROUP BY gid", (user.lower(),)):
        trained[r["gid"]] = r["n"]
    out = []
    for g in reversed(games):
        w = book.walk(g)
        depth = eng.deepest_cached(g, 1)
        s = _summary(g, depth) if depth > 1 else None
        reason = s["reason"] if s else None
        ov = overrides.get(g.game_id)
        if ov and ov.get("primary"):
            reason = ov["primary"]
        out.append({
            "id": g.game_id, "date": g.date, "color": g.color, "opponent": g.opponent,
            "opp_elo": g.opp_elo, "elo": g.user_elo, "result": g.result,
            "outcome": g.outcome, "time_class": g.time_class,
            "moves": (len(g.moves) + 1) // 2, "opening": w.family, "line": w.name,
            "eco": w.eco, "ending": g.termination,
            "accuracy": s["accuracy"] if s else None,
            "opp_accuracy": s["opp_accuracy"] if s else None,
            "blunders": s["blunders"] if s else None,
            "reason": reason,
            "reason_label": dx.reason_label(g.outcome, reason) if reason else None,
            "depth": s["depth"] if s else None,
            "positions": trained.get(str(g.game_id), 0),
            **(flags.get(str(g.game_id)) or {}),
        })
    return out
