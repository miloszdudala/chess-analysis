"""Opponents closed by Chess.com for fair-play violations.

Chess.com publishes an account's standing on its profile: a player caught
cheating has `status == "closed:fair_play_violations"`. That is the only
authoritative source for "was this opponent cheating" — far better than
guessing from the moves — so games against those accounts are detected rather
than flagged by hand.

Statuses are kept in the store and refreshed during a sync, so the rest of the app
(and `model.load_games` in particular) reads them without ever touching the
network. A ban is permanent, so once an account is seen closed it is never
re-checked.

How soon a clean status is re-checked depends on how recently you played the
account, because that is when the answer can still change. Chess.com closes an
account days to weeks after the games that got it closed, so an opponent from
last week is precisely the one whose status is about to flip — cache that for a
week and the ban lands inside the blind spot. Opponents played in the last
`RECENT_DAYS` are therefore re-checked every `RECENT_TTL_HOURS`; older ones
keep the cheap `TTL_DAYS`. It costs one request per recent opponent per day.
"""
from __future__ import annotations

import calendar
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import store

API = "https://api.chess.com/pub"
HEADERS = {"User-Agent": "Personal storage"}

BANNED = "closed:fair_play_violations"
FLAG = "cheat"
LABEL = "Opponent banned for fair play — doesn't count toward stats"

TTL_DAYS = 7                 # an opponent from long ago: settled, check rarely
RECENT_DAYS = 45             # ...but a ban usually lands within weeks of the game
RECENT_TTL_HOURS = 12
_TTL = TTL_DAYS * 86400
_RECENT_TTL = RECENT_TTL_HOURS * 3600
_RECENT = RECENT_DAYS * 86400


def _fetch_status(username: str) -> str | None:
    """One profile lookup. None if the account is unreadable (404, network)."""
    url = f"{API}/player/{urllib.parse.quote(username)}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp).get("status")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def status(username: str) -> str | None:
    """Cached profile status for one account, or None if never looked up."""
    entry = store.kv_get("fairplay", username.lower())
    return (entry or {}).get("status")


def is_banned(username: str) -> bool:
    return status(username) == BANNED


def _stale(entry: dict | None, recent: bool = False) -> bool:
    """Does this cached status need another lookup? Bans never do."""
    if not entry:
        return True
    if entry.get("status") == BANNED:
        return False                      # a ban is permanent
    ttl = _RECENT_TTL if recent else _TTL
    return time.time() - entry.get("checked", 0) > ttl


def _epoch(stamp: str) -> int:
    """'2026.09.05 12:00:00' -> unix time, 0 if unparseable."""
    try:
        return calendar.timegm(time.strptime(stamp, "%Y.%m.%d %H:%M:%S"))
    except ValueError:
        return 0


def opponents_of(games) -> list[tuple[str, int]]:
    """(opponent, when you last played them) — what `refresh` wants."""
    latest: dict[str, int] = {}
    for g in games:
        if not g.opponent:
            continue
        name = g.opponent.lower()
        latest[name] = max(latest.get(name, 0), _epoch(g.sort_key))
    return sorted(latest.items())


def refresh(opponents, log=None) -> dict:
    """Look up every opponent whose cached status is missing or stale.

    `opponents` is names, or (name, last-played unix time) pairs from
    `opponents_of` — with the timestamps, recently-played accounts are
    re-checked far more often, which is the whole point (see module docstring).

    Returns {"checked": n, "banned": [usernames]} — `banned` lists everyone
    known to be closed, not only the ones looked up on this call.
    """
    played: dict[str, int] = {}
    for o in opponents:
        name, ts = (o[0], o[1]) if isinstance(o, (tuple, list)) else (o, 0)
        if name:
            played[name.lower()] = max(played.get(name.lower(), 0), ts or 0)

    now = time.time()
    checked = 0
    for name in sorted(played):
        recent = bool(played[name]) and (now - played[name]) < _RECENT
        entry = store.kv_get("fairplay", name)
        if _stale(entry, recent):
            st = _fetch_status(name)
            checked += 1
            if st is not None:
                store.kv_set("fairplay", name, {"status": st, "checked": time.time()})
                if st == BANNED and log:
                    log(f"  {name}: banned for fair-play violations")
            time.sleep(0.2)               # be polite to the API
    return {"checked": checked,
            "banned": sorted(n for n in played if is_banned(n))}


def cheated_ids(games) -> set[str]:
    """Ids of games played against an account since closed for cheating."""
    return {str(g.game_id) for g in games if g.opponent and is_banned(g.opponent)}


def flags(games) -> dict[str, dict]:
    """{game_id: {"flag": "cheat", "note": ...}} in the same shape as
    `overrides.flags()`, so the history and recent-games views mark these
    exactly like a hand-flagged game."""
    return {str(g.game_id): {"flag": FLAG,
                             "note": f"{g.opponent} was banned for fair play"}
            for g in games if g.opponent and is_banned(g.opponent)}
