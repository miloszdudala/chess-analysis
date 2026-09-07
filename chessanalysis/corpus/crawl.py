"""Filling the corpus: a rating-greedy walk over the opponent graph.

Not a breadth-first search. Each step asks which band is furthest below its
quota and then picks the cheapest source for that band, because two facts make
that far more efficient than fanning out evenly:

  * one monthly archive is a single request that yields 35-260 games AND ~250
    opponent names already labelled with their rating, so discovering
    candidates costs nothing;
  * a single account's archives span its whole career — one player observed
    here ran 601 to 1747 across five years — so reaching a low band means
    walking back through a player already known, not finding new ones.

Games are sampled for even pairings: chess.com pairs closely, and a lopsided
game is atypical of either player's band. A minority of stretched pairings is
kept on purpose so the corpus isn't only mirror matches.
"""
from __future__ import annotations

import json
import math
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import model, store
from . import BAND_SIZE, TIME_CONTROL

API = "https://api.chess.com/pub"
HEADERS = {"User-Agent": "Personal storage"}

# A 10-minute game decided inside 8 moves is an abort or a disconnect, not a
# game anyone played — about 2% of a raw archive, and they would wreck the
# opening statistics (a 0-ply "resignation" scores as a loss with no moves).
MIN_PLIES = 16
GAMES_PER_PLAYER = 10       # nobody's style dominates a band
GAP_TIGHT, GAP_LOOSE, GAP_LOOSE_P = 30, 80, 0.30
PEERS_SD, PEERS_HALFWIDTH = 55, 110

_rnd = random.Random()


def _get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5 * (i + 1))
                continue
            return None
        except Exception:                       # noqa: BLE001
            time.sleep(1 + i)
    return None


def _json(url):
    b = _get(url)
    try:
        return json.loads(b) if b else None
    except json.JSONDecodeError:
        return None


def _text(url):
    b = _get(url)
    return b.decode("utf-8", "replace") if b else None


def plan(user_elo: int, bands: int = 2) -> dict:
    """Quota targets: your own band densely, the ladder around it evenly."""
    home = user_elo // BAND_SIZE * BAND_SIZE
    return {b: 0 for b in range(home - bands * BAND_SIZE,
                                home + (bands + 1) * BAND_SIZE, BAND_SIZE)}


def targets(my_elo: int, depth: int, bands: int = 2, floor: int = 300) -> dict:
    """Aim every nearby band at whatever the best-covered one already has.

    Expansion then always flows to the thinnest band rather than deepening one
    that is already rich, which is what makes the ladder comparable end to end.
    """
    have = {r["band"]: r["samples"] for r in _coverage(store.connect(), depth)}
    top = max(list(have.values()) + [floor])
    return {b: top for b in plan(my_elo, bands)}


def _status(conn, name):
    row = conn.execute("SELECT status FROM players WHERE username=?", (name,)).fetchone()
    if row and row[0]:
        return row[0]
    st = (_json(f"{API}/player/{urllib.parse.quote(name)}") or {}).get("status") or "unknown"
    conn.execute("INSERT INTO players(username,status,checked) VALUES(?,?,?) "
                 "ON CONFLICT(username) DO UPDATE SET status=excluded.status,"
                 " checked=excluded.checked", (name, st, time.time()))
    time.sleep(0.18)
    return st


def _gap_ok(gap):
    if gap <= GAP_TIGHT:
        return True
    return gap <= GAP_LOOSE and _rnd.random() < GAP_LOOSE_P


def _peers_ok(level, welo, belo, my_elo):
    if abs(welo - my_elo) > PEERS_HALFWIDTH or abs(belo - my_elo) > PEERS_HALFWIDTH:
        return False
    return _rnd.random() < math.exp(-((level - my_elo) ** 2) / (2 * PEERS_SD ** 2))


def _need(conn, targets, depth):
    """Bands below quota, emptiest first."""
    have = {r["band"]: r["samples"] for r in _coverage(conn, depth)}
    open_ = [(b, t, have.get(b, 0)) for b, t in targets.items() if have.get(b, 0) < t]
    open_.sort(key=lambda x: x[2] / max(x[1], 1))
    return open_


def _coverage(conn, depth):
    return [{"band": r[0], "samples": r[1]} for r in conn.execute(
        "SELECT s.band, COUNT(*) FROM samples s JOIN games g ON g.gid=s.gid "
        "WHERE g.source='corpus' AND s.depth=? AND s.band IS NOT NULL GROUP BY s.band",
        (depth,))]


def _pick(conn, want_rating):
    rows = conn.execute(
        "SELECT f.username, f.rating FROM frontier f "
        "LEFT JOIN players p ON p.username=f.username "
        "WHERE COALESCE(p.taken,0) < ? AND COALESCE(p.tried,0) < 3 "
        "  AND COALESCE(p.status,'ok') NOT LIKE 'closed%' "
        "ORDER BY ABS(f.rating - ?) LIMIT 40", (GAMES_PER_PLAYER, want_rating)).fetchall()
    return _rnd.choice(rows[:12]) if rows else None


def _archives(conn, name):
    row = conn.execute("SELECT archives FROM players WHERE username=?", (name,)).fetchone()
    if row and row[0]:
        return json.loads(row[0])
    arch = (_json(f"{API}/player/{name}/games/archives") or {}).get("archives", [])
    conn.execute("INSERT INTO players(username,archives) VALUES(?,?) "
                 "ON CONFLICT(username) DO UPDATE SET archives=excluded.archives",
                 (name, json.dumps(arch)))
    time.sleep(0.18)
    return arch


def seed(conn, user: str) -> None:
    """Prime the frontier from the accounts you have actually played."""
    for g in model.load_games(user, include_flagged=True):
        if g.opponent and g.opp_elo:
            conn.execute("INSERT INTO frontier(username,rating,seen) VALUES(?,?,?) "
                         "ON CONFLICT(username) DO UPDATE SET rating=excluded.rating",
                         (g.opponent.lower(), g.opp_elo, time.time()))
    conn.commit()


def _harvest(conn, name, rating, targets, my_elo, depth, budget_left):
    """Fetch one unspent month; bank what it can fill a quota with."""
    if _status(conn, name).startswith("closed"):
        conn.execute("UPDATE players SET tried=tried+3 WHERE username=?", (name,))
        return 0
    arch = _archives(conn, name)
    row = conn.execute("SELECT spent, taken FROM players WHERE username=?",
                       (name,)).fetchone()
    spent = set(json.loads(row[0])) if row and row[0] else set()
    taken = (row[1] if row else 0) or 0
    fresh = [a for a in arch[-8:] if a not in spent]
    if not fresh:
        conn.execute("UPDATE players SET tried=tried+3 WHERE username=?", (name,))
        return 0
    url = _rnd.choice(fresh[-4:])
    text = _text(url.rstrip("/") + "/pgn")
    spent.add(url)
    conn.execute("UPDATE players SET spent=?, tried=tried+1 WHERE username=?",
                 (json.dumps(sorted(spent)), name))
    time.sleep(0.3)
    if not text:
        return 0

    open_ = {b: t - h for b, t, h in _need(conn, targets, depth)}
    budget = min(GAMES_PER_PLAYER - taken, budget_left)
    cands = []
    for g in model.parse_pgn_text(text):
        row = model.game_row(g, source="corpus")
        if (row["time_control"] != TIME_CONTROL or row["welo"] is None
                or row["belo"] is None or row["plies"] < MIN_PLIES
                or row["result"] not in ("1-0", "0-1", "1/2-1/2")):
            continue
        for who, elo in ((row["white"], row["welo"]), (row["black"], row["belo"])):
            if who != name:
                conn.execute("INSERT INTO frontier(username,rating,seen) VALUES(?,?,?) "
                             "ON CONFLICT(username) DO UPDATE SET rating=excluded.rating",
                             (who, elo, time.time()))
        cands.append(row)

    _rnd.shuffle(cands)                       # spread across the month, not its tail
    cands.sort(key=lambda r: r["gap"])        # then evenest pairings first
    banked = 0
    for row in cands:
        if banked >= budget:
            break
        if store.has_game(row["gid"]) or not _gap_ok(row["gap"]):
            continue
        level = row["level"]
        # a game counts twice: once per side, so it can serve two bands
        serves = {row["welo"] // BAND_SIZE * BAND_SIZE,
                  row["belo"] // BAND_SIZE * BAND_SIZE}
        if not (any(open_.get(b, 0) > 0 for b in serves)
                or _peers_ok(level, row["welo"], row["belo"], my_elo)):
            continue
        if any(_status(conn, x).startswith("closed") for x in (row["white"], row["black"])):
            continue
        store.save_games([row])
        conn.execute("UPDATE players SET taken=COALESCE(taken,0)+1, rating=? "
                     "WHERE username=?", (rating, name))
        for b in serves:
            open_[b] = open_.get(b, 0) - 1
        banked += 1
    conn.commit()
    return banked


def expand(n: int, user: str, my_elo: int, targets: dict, depth: int,
           log=lambda s: None, should_stop=lambda: False) -> int:
    """Bank up to `n` new corpus games. Returns how many were banked."""
    conn = store.connect()
    if conn.execute("SELECT COUNT(*) FROM frontier").fetchone()[0] < 50:
        seed(conn, user)
    banked, stall = 0, 0
    while banked < n and stall < 40 and not should_stop():
        open_ = _need(conn, targets, depth)
        want = my_elo if not open_ else open_[0][0] + BAND_SIZE // 2
        pick = _pick(conn, want)
        if not pick:
            log("frontier exhausted")
            break
        got = _harvest(conn, pick[0], pick[1], targets, my_elo, depth, n - banked)
        banked += got
        stall = 0 if got else stall + 1
        log(f"{pick[0]} (r{pick[1]}) +{got} — {banked}/{n}")
    return banked
