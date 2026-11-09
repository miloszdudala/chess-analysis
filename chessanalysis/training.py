"""Training from your own games: the positions you got wrong, until you don't.

Three kinds of position are drawn from your analysed games:

* **mistake** — you played a move that cost 12% or more of your win chance;
  the task is to find what you should have played.
* **missed** — your opponent had just handed you 15% or more and your reply
  gave a real part of it back; the task is to take what was offered.
* **opening** — a position you reached at least twice in the opening and
  answered the same costly way each time; the task is to fix the habit.

A move counts as solved when it keeps the win chance within `TOLERANCE`
points of the engine's best — so any equally good move is right, not only
the one the engine happened to list first. Moves the stored analysis does not
cover are judged by the live engine.

Positions come back on a spaced-repetition schedule (a simplified SM-2): a
position solved first time comes back after a day, then three, then at a
growing interval; one you missed comes back within the session.

The labels attached to a position are only the ones the engine output
proves — a forced mate, a single good move, the phase, whether you were
ahead or behind — never a guessed tactical motif.
"""
from __future__ import annotations

import hashlib
import json
import time

import chess

from . import store
from .enrich.engine import MATE_CP, win_prob

KINDS = {"mistake": "Your mistakes", "missed": "Missed chances",
         "opening": "Opening fixes"}
MIN_LOSS = 12.0        # win% a move must lose to be worth drilling
GIFT = 15.0            # win% the opponent's move must hand over...
GAVE_BACK = 8.0        # ...and how much of it your reply must give back
DECIDED = 3.0          # skip positions already within this of 0% or 100%
TOLERANCE = 5.0        # a move within this many win% of the best is solved
ONLY_MOVE = 15.0       # the second-best move is this much worse: "only move"
OPENING_PLY = 24       # opening fixes come from the first twelve moves
OPENING_MIN_TIMES = 2
OPENING_MIN_CPL = 40
NEW_PER_DAY = 20
DAY = 86400.0
RELEARN = 600.0        # a missed position comes back after ten minutes


# --- extraction -----------------------------------------------------------------

def _mover_wp(cp_white: int, white_to_move: bool) -> float:
    return win_prob(cp_white if white_to_move else -cp_white)


def _mate_in(cp_white: int, white_to_move: bool) -> int | None:
    """Moves to mate for the side to move, from a white-POV mate score."""
    cp = cp_white if white_to_move else -cp_white
    if cp >= MATE_CP - 500:            # python-chess: Mate(n) scores MATE_CP - n
        return max(1, MATE_CP - cp)
    return None


def _solutions(top, white_to_move, best_wp):
    """The engine's candidates that count as solving the position."""
    return [t for t in top if best_wp - _mover_wp(t["cp"], white_to_move) <= TOLERANCE]


def _themes(a, ply, top, white_to_move, wp_before, kind):
    themes = [a.phase_of(ply)]
    mate = _mate_in(top[0]["cp"], white_to_move)
    if mate:
        themes.append(f"Mate in {mate}")
    if len(top) >= 2:
        gap = _mover_wp(top[0]["cp"], white_to_move) - _mover_wp(top[1]["cp"], white_to_move)
        if gap >= ONLY_MOVE:
            themes.append("Only move")
    if kind != "opening":
        if wp_before >= 65:
            themes.append("Converting")
        elif wp_before <= 35:
            themes.append("Defending")
    return themes


def _san(fen, uci):
    try:
        b = chess.Board(fen)
        return b.san(chess.Move.from_uci(uci))
    except (ValueError, AssertionError):
        return uci


def _context(g, a, ply):
    """What the board shows before the task: the opponent's last move."""
    prev = ply - 1
    return {
        "prev_fen": a.fens[prev - 1] if prev >= 1 else None,
        "prev_uci": a.moves[prev - 1].move_uci if prev >= 1 else None,
        "prev_san": a.moves[prev - 1].san if prev >= 1 else None,
    }


def _game_info(g, ply):
    return {"opponent": g.opponent, "opp_elo": g.opp_elo, "date": g.date,
            "color": g.color, "outcome": g.outcome, "move_no": (ply + 1) // 2,
            "time_class": g.time_class}


def _from_game(g, a) -> list[dict]:
    """Every mistake / missed-chance position of `g`'s player in one game."""
    out = []
    if not a.top_moves or not a.fens:
        return out
    for i, m in enumerate(a.moves):
        if m.color != g.color:
            continue
        ply = m.ply
        top = a.top_moves[ply - 1] if ply - 1 < len(a.top_moves) else []
        if len(top) < 2 or not m.move_uci:
            continue                   # one-candidate (bulk) analyses can't grade
        white = m.color == "white"
        wp_before = _mover_wp(a.evals[ply - 1], white)
        if wp_before <= DECIDED or wp_before >= 100 - DECIDED:
            continue
        best_wp = _mover_wp(top[0]["cp"], white)
        prev = a.moves[i - 1] if i else None
        missed = (prev is not None and prev.color != g.color and prev.wp_loss >= GIFT
                  and m.wp_loss >= GAVE_BACK)
        if not missed and m.wp_loss < MIN_LOSS:
            continue
        sols = _solutions(top, white, best_wp)
        if m.move_uci in {s["uci"] for s in sols}:
            continue                   # what you played was fine after all
        kind = "missed" if missed else "mistake"
        fen = a.fens[ply - 1]
        out.append({
            "id": f"{g.game_id}:{ply}", "gid": str(g.game_id), "ply": ply,
            "kind": kind, "fen": fen, "solution": top[0]["uci"],
            "data": {
                "best": [{"uci": t["uci"], "san": _san(fen, t["uci"]), "cp": t["cp"]}
                         for t in sols],
                "top": [{"uci": t["uci"], "san": _san(fen, t["uci"]), "cp": t["cp"]}
                        for t in top],
                "played": {"uci": m.move_uci, "san": m.san,
                           "loss": round(m.wp_loss, 1), "cp_after": a.evals[ply]},
                "gift": round(prev.wp_loss, 1) if missed else None,
                "wp_before": round(wp_before, 1), "cp_before": a.evals[ply - 1],
                "themes": _themes(a, ply, top, white, wp_before, kind),
                "game": _game_info(g, ply), **_context(g, a, ply),
                "depth": a.depth,
            },
        })
    return out


def _openings(pairs) -> list[dict]:
    """Repeated, costly opening habits: one position per (position, move)."""
    spots: dict = {}
    for g, a in pairs:
        if not a.top_moves:
            continue
        for m in a.moves:
            if m.color != g.color or m.ply > OPENING_PLY or not m.fen_before:
                continue
            key = (" ".join(m.fen_before.split()[:4]), m.san)
            spots.setdefault(key, []).append((g, a, m))
    out = []
    for (fen_key, san), hits in spots.items():
        if len(hits) < OPENING_MIN_TIMES:
            continue
        if sum(m.cp_loss for _, _, m in hits) / len(hits) < OPENING_MIN_CPL:
            continue
        g, a, m = max(hits, key=lambda h: h[0].sort_key)      # the latest time
        top = a.top_moves[m.ply - 1] if m.ply - 1 < len(a.top_moves) else []
        if len(top) < 2:
            continue
        white = m.color == "white"
        sols = _solutions(top, white, _mover_wp(top[0]["cp"], white))
        if m.move_uci in {s["uci"] for s in sols}:
            continue
        fen = a.fens[m.ply - 1]
        pid = "open:" + hashlib.sha1(f"{fen_key}|{san}".encode()).hexdigest()[:16]
        out.append({
            "id": pid, "gid": str(g.game_id), "ply": m.ply, "kind": "opening",
            "fen": fen, "solution": top[0]["uci"],
            "data": {
                "best": [{"uci": t["uci"], "san": _san(fen, t["uci"]), "cp": t["cp"]}
                         for t in sols],
                "top": [{"uci": t["uci"], "san": _san(fen, t["uci"]), "cp": t["cp"]}
                        for t in top],
                "played": {"uci": m.move_uci, "san": m.san,
                           "loss": round(sum(h[2].wp_loss for h in hits) / len(hits), 1),
                           "cp_after": a.evals[m.ply]},
                "times": len(hits),
                "record": {o: sum(1 for h in hits if h[0].outcome == o)
                           for o in ("win", "draw", "loss")},
                "wp_before": round(_mover_wp(a.evals[m.ply - 1], white), 1),
                "cp_before": a.evals[m.ply - 1],
                "themes": _themes(a, m.ply, top, white, 50, "opening"),
                "game": _game_info(g, m.ply), **_context(g, a, m.ply),
                "depth": a.depth,
            },
        })
    return out


def _analysed(user, min_depth=12):
    """(Game, GameAnalysis) for every counted game with a multi-candidate
    analysis on record — the deepest one. Bullet games count from their own,
    shallower review depth."""
    from .enrich import engine as eng
    from .model import load_games

    pairs = []
    for g in load_games(user):
        depth = eng.deepest_cached(g, min(min_depth, eng.review_depth(g)))
        raw = store.load_analysis(g.game_id, depth)
        if raw and raw.get("evals") and raw.get("top_moves"):
            pairs.append((g, eng._derive(raw, depth, raw.get("engine_name", "cache"))))
    return pairs


def candidates(user: str) -> list[dict]:
    pairs = _analysed(user)
    out = []
    for g, a in pairs:
        out += _from_game(g, a)
    return out + _openings(pairs)


def sync(user: str) -> dict:
    """Add any new positions from your games to your training set."""
    user = user.lower()
    conn = store.connect()
    now = time.time()
    found = candidates(user)
    before = conn.execute("SELECT COUNT(*) FROM puzzles WHERE user=?", (user,)).fetchone()[0]
    conn.executemany(
        "INSERT OR IGNORE INTO puzzles(id,user,gid,ply,kind,fen,solution,data,created,due) "
        "VALUES(?,?,?,?,?,?,?,?,?,NULL)",
        [(p["id"], user, p["gid"], p["ply"], p["kind"], p["fen"], p["solution"],
          json.dumps(p["data"], separators=(",", ":")), now) for p in found])
    # refresh the stored facts (a deeper analysis may have arrived) but never
    # the schedule
    conn.executemany("UPDATE puzzles SET data=?, solution=? WHERE id=? AND user=?",
                     [(json.dumps(p["data"], separators=(",", ":")), p["solution"],
                       p["id"], user) for p in found])
    # a position can stop qualifying (the game was flagged, a deeper search
    # found your move fine): retire it rather than drill a non-mistake
    live = {p["id"] for p in found}
    stale = [r[0] for r in conn.execute(
        "SELECT id FROM puzzles WHERE user=? AND retired=0", (user,)) if r[0] not in live]
    conn.executemany("UPDATE puzzles SET retired=1 WHERE id=? AND user=?",
                     [(i, user) for i in stale])
    conn.executemany("UPDATE puzzles SET retired=0 WHERE id=? AND user=? AND retired=1",
                     [(i, user) for i in live])
    conn.commit()
    added = conn.execute("SELECT COUNT(*) FROM puzzles WHERE user=?", (user,)).fetchone()[0] - before
    return {"added": added, **summary(user)}


# --- the schedule ---------------------------------------------------------------------

def _row(r) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"])
    return d


def summary(user: str) -> dict:
    user = user.lower()
    now = time.time()
    rows = [_row(r) for r in store.connect().execute(
        "SELECT * FROM puzzles WHERE user=? AND retired=0", (user,))]
    new_today = _new_seen_today(user)
    by_kind = {k: {"total": 0, "due": 0, "new": 0, "learned": 0} for k in KINDS}
    for r in rows:
        k = by_kind[r["kind"]]
        k["total"] += 1
        if r["last"] is None:
            k["new"] += 1
        elif r["due"] is not None and r["due"] <= now:
            k["due"] += 1
        if r["interval"] and r["interval"] >= 21:
            k["learned"] += 1
    phases: dict = {}
    for r in rows:
        ph = r["data"]["themes"][0]
        phases[ph] = phases.get(ph, 0) + 1
    due = sum(k["due"] for k in by_kind.values())
    new = sum(k["new"] for k in by_kind.values())
    return {"total": len(rows), "due": due, "new": new,
            "new_left_today": max(0, NEW_PER_DAY - new_today),
            "learned": sum(k["learned"] for k in by_kind.values()),
            "by_kind": by_kind, "by_phase": phases, "kinds": KINDS,
            "streak": _streak(user),
            "rules": {"min_loss": MIN_LOSS, "gift": GIFT, "tolerance": TOLERANCE}}


def _new_seen_today(user):
    start = time.time() - time.time() % DAY
    return store.connect().execute(
        "SELECT COUNT(*) FROM puzzles WHERE user=? AND reps+lapses<=1 AND last>=? "
        "AND created IS NOT NULL", (user, start)).fetchone()[0]


def _streak(user) -> int:
    """Consecutive days, ending today or yesterday, with at least one review."""
    days = {int(r[0] // DAY) for r in store.connect().execute(
        "SELECT last FROM puzzles WHERE user=? AND last IS NOT NULL", (user,))}
    today = int(time.time() // DAY)
    d = today if today in days else today - 1
    n = 0
    while d in days:
        n += 1
        d -= 1
    return n


def next_puzzle(user: str, kind: str | None = None, phase: str | None = None,
                theme: str | None = None, game: str | None = None,
                exclude: str | None = None) -> dict | None:
    """The next position to work on: anything due first (oldest due first),
    then new positions — the costliest first — while today's allowance lasts.
    Without either, the position due soonest, so a session can continue.

    Filters narrow the pool: `kind`, `phase` ("Middlegame"), `theme`
    ("Converting") or one `game` id — a game's own positions in move order,
    ignoring the schedule, since reviewing a game is its own session.
    """
    user = user.lower()
    now = time.time()
    where, args = "user=? AND retired=0", [user]
    if kind:
        where += " AND kind=?"
        args.append(kind)
    if game:
        where += " AND gid=? AND kind<>'opening'"
        args.append(str(game))
    if exclude:
        where += " AND id<>?"
        args.append(exclude)
    rows = [_row(r) for r in store.connect().execute(
        f"SELECT * FROM puzzles WHERE {where}", args)]
    if phase:
        rows = [r for r in rows if r["data"]["themes"][0] == phase]
    if theme:
        rows = [r for r in rows if theme in r["data"]["themes"]]
    if not rows:
        return None
    if game:
        seen_today = time.time() - time.time() % DAY
        todo = sorted((r for r in rows if not r["last"] or r["last"] < seen_today),
                      key=lambda r: r["ply"])
        return _public(todo[0], "game") if todo else None
    due = sorted((r for r in rows if r["last"] is not None and r["due"] is not None
                  and r["due"] <= now), key=lambda r: r["due"])
    if due:
        return _public(due[0], "review")
    fresh = [r for r in rows if r["last"] is None]
    if fresh and _new_seen_today(user) < NEW_PER_DAY:
        fresh.sort(key=lambda r: (-(r["data"]["played"]["loss"] or 0), r["gid"]))
        return _public(fresh[0], "new")
    upcoming = sorted((r for r in rows if r["due"] is not None), key=lambda r: r["due"])
    if upcoming:
        return _public(upcoming[0], "ahead")
    return _public(fresh[0], "new") if fresh else None


def _public(r, status) -> dict:
    """A puzzle as the board sees it — without the answer."""
    d = r["data"]
    return {"id": r["id"], "kind": r["kind"], "kind_label": KINDS[r["kind"]],
            "fen": r["fen"], "gid": r["gid"], "ply": r["ply"], "status": status,
            "themes": d["themes"], "game": d["game"], "prev_fen": d.get("prev_fen"),
            "prev_uci": d.get("prev_uci"), "prev_san": d.get("prev_san"),
            "times": d.get("times"), "gift": d.get("gift"),
            "played_san": d["played"]["san"], "played_loss": d["played"]["loss"],
            "reps": r["reps"], "lapses": r["lapses"],
            "turn": "white" if " w " in r["fen"] else "black"}


def get(user: str, pid: str) -> dict | None:
    r = store.connect().execute("SELECT * FROM puzzles WHERE id=? AND user=?",
                                (pid, user.lower())).fetchone()
    return _row(r) if r else None


def attempt(user: str, pid: str, uci: str, live=None) -> dict:
    """Judge one move. `live(fen, uci)` is the engine fallback for moves the
    stored analysis does not cover (see `livengine.after_move`)."""
    from . import livengine

    p = get(user, pid)
    if p is None:
        raise ValueError("unknown puzzle")
    d = p["data"]
    board = chess.Board(p["fen"])
    mv = livengine.parse_move(board, uci)
    if mv is None:
        return {"legal": False}
    white = board.turn == chess.WHITE
    best_wp = _mover_wp(d["top"][0]["cp"], white)
    san = board.san(mv)
    known = {t["uci"]: t for t in d["top"]}
    after = board.copy()
    after.push(mv)
    if after.is_checkmate():
        cp, source = (MATE_CP if white else -MATE_CP), "mate"
    elif mv.uci() in known:
        cp, source = known[mv.uci()]["cp"], "analysis"
    else:
        res = (live or livengine.after_move)(p["fen"], mv.uci())
        cp, source = res["cp"], "engine"
    wp = _mover_wp(cp, white)
    solved = best_wp - wp <= TOLERANCE
    return {"legal": True, "solved": solved, "uci": mv.uci(), "san": san,
            "cp": cp, "loss": round(max(0.0, best_wp - wp), 1), "source": source,
            "fen_after": after.fen()}


def reveal(user: str, pid: str) -> dict:
    """The answer, and how the game actually went from here."""
    from . import livengine

    p = get(user, pid)
    if p is None:
        raise ValueError("unknown puzzle")
    d = p["data"]
    line = []
    try:
        res = livengine.analyse(p["fen"], depth=16, multipv=1, pv_len=8)
        if res["best"]:
            line = res["best"][0].get("pv", [])
    except Exception:                       # noqa: BLE001 — no engine: no line
        line = []
    return {"best": d["best"], "played": d["played"], "line": line,
            "cp_before": d["cp_before"], "times": d.get("times"),
            "record": d.get("record"), "gid": p["gid"], "ply": p["ply"]}


def grade(user: str, pid: str, result: str, now: float | None = None) -> dict:
    """Schedule a position after a session: "good" (solved first time),
    "hard" (solved after a retry or a hint) or "fail"."""
    if result not in ("good", "hard", "fail"):
        raise ValueError(f"unknown grade '{result}'")
    now = now or time.time()
    p = get(user, pid)
    if p is None:
        raise ValueError("unknown puzzle")
    interval, ease = p["interval"] or 0.0, p["ease"] or 2.5
    reps, lapses = p["reps"] or 0, p["lapses"] or 0
    if result == "good":
        interval = 1.0 if reps == 0 else 3.0 if reps == 1 else interval * ease
        ease = min(3.0, ease + 0.05)
        reps += 1
        due = now + interval * DAY
    elif result == "hard":
        interval = max(1.0, interval * 1.2)
        ease = max(1.3, ease - 0.15)
        reps += 1
        due = now + interval * DAY
    else:
        interval, reps, lapses = 0.0, 0, lapses + 1
        ease = max(1.3, ease - 0.2)
        due = now + RELEARN
    conn = store.connect()
    conn.execute("UPDATE puzzles SET interval=?, ease=?, reps=?, lapses=?, due=?, "
                 "last=?, grade=? WHERE id=? AND user=?",
                 (interval, ease, reps, lapses, due, now, result, pid, user.lower()))
    conn.commit()
    return {"id": pid, "interval": interval, "due": due, "ease": round(ease, 2)}


def for_game(user: str, gid: str) -> list[dict]:
    """The training positions that came from one game (for its review)."""
    return [{"id": r["id"], "ply": r["ply"], "kind": r["kind"],
             "themes": json.loads(r["data"])["themes"]}
            for r in store.connect().execute(
                "SELECT id, ply, kind, data FROM puzzles WHERE user=? AND gid=? "
                "AND retired=0 AND kind<>'opening' ORDER BY ply",
                (user.lower(), str(gid)))]
