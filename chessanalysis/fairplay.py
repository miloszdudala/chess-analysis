"""Opponents closed by Chess.com for fair-play violations.

Chess.com publishes an account's standing on its profile: a player caught
cheating has `status == "closed:fair_play_violations"`. That is the only
authoritative source for "was this opponent cheating" — far better than
guessing from the moves — so games against those accounts are detected rather
than flagged by hand.

Statuses are cached on disk and refreshed during a sync, so the rest of the app
(and `model.load_games` in particular) reads them without ever touching the
network. A ban is permanent, so once an account is seen closed it is never
re-checked; every other status is re-checked after `TTL_DAYS`, since the player
you faced today may be banned next week.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import cache

API = "https://api.chess.com/pub"
HEADERS = {"User-Agent": "Personal storage"}

BANNED = "closed:fair_play_violations"
FLAG = "cheat"
LABEL = "Opponent banned for fair play — doesn't count toward stats"

TTL_DAYS = 7
_TTL = TTL_DAYS * 86400


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
    entry = cache.load("fairplay", username.lower())
    return (entry or {}).get("status")


def is_banned(username: str) -> bool:
    return status(username) == BANNED


def _stale(entry: dict | None) -> bool:
    """Does this cached status need another lookup? Bans never do."""
    if not entry:
        return True
    if entry.get("status") == BANNED:
        return False                      # a ban is permanent
    return time.time() - entry.get("checked", 0) > _TTL


def refresh(opponents, log=None) -> dict:
    """Look up every opponent whose cached status is missing or stale.

    Returns {"checked": n, "banned": [usernames]} — `banned` lists everyone
    known to be closed, not only the ones looked up on this call.
    """
    checked = 0
    for name in sorted({o.lower() for o in opponents if o}):
        entry = cache.load("fairplay", name)
        if _stale(entry):
            st = _fetch_status(name)
            checked += 1
            if st is not None:
                cache.save("fairplay", name, {"status": st, "checked": time.time()})
                if st == BANNED and log:
                    log(f"  {name}: banned for fair-play violations")
            time.sleep(0.2)               # be polite to the API
    banned = sorted({o.lower() for o in opponents if o and is_banned(o)})
    return {"checked": checked, "banned": banned}


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
