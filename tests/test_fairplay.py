"""Detecting opponents Chess.com has closed for fair-play violations."""
from __future__ import annotations

import time

import pytest

from chessanalysis import fairplay, store


class FakeGame:
    def __init__(self, gid, opponent):
        self.game_id = gid
        self.opponent = opponent


@pytest.fixture
def offline(monkeypatch):
    """A recorded, scripted profile API (the store is isolated per test)."""
    calls = []

    def fake_fetch(username):
        calls.append(username)
        if username == "ghost":
            return None
        status = fairplay.BANNED if username == "cheat" else "basic"
        return {"status": status, "country": "PL"}

    monkeypatch.setattr(fairplay, "_fetch_profile", fake_fetch)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return calls


def test_refresh_reports_who_is_banned(offline):
    res = fairplay.refresh(["cheat", "honest"])
    assert res["banned"] == ["cheat"]
    assert res["checked"] == 2
    assert fairplay.is_banned("cheat")
    assert not fairplay.is_banned("honest")


def test_lookups_are_cached_so_a_resync_costs_nothing(offline):
    fairplay.refresh(["cheat", "honest"])
    offline.clear()
    fairplay.refresh(["cheat", "honest"])
    assert offline == []


def test_a_clean_status_is_rechecked_once_it_goes_stale(offline):
    fairplay.refresh(["honest"])
    stale = time.time() - (fairplay.TTL_DAYS + 1) * 86400
    store.kv_set("fairplay", "honest", {"status": "basic", "country": "PL", "checked": stale})
    offline.clear()
    fairplay.refresh(["honest"])
    assert offline == ["honest"]


def test_the_country_is_kept_with_the_status(offline):
    fairplay.refresh(["Honest"])
    assert fairplay.country("honest") == "PL"


def test_an_entry_cached_before_countries_is_looked_up_once_more(offline):
    store.kv_set("fairplay", "honest", {"status": "basic", "checked": time.time()})
    fairplay.refresh(["honest"])
    assert offline == ["honest"]
    offline.clear()
    fairplay.refresh(["honest"])
    assert offline == []


def test_a_ban_is_permanent_and_never_rechecked(offline):
    fairplay.refresh(["cheat"])
    store.kv_set("fairplay", "cheat", {"status": fairplay.BANNED, "checked": 0})
    offline.clear()
    fairplay.refresh(["cheat"])
    assert offline == []


def test_an_unreadable_profile_is_not_cached(offline):
    fairplay.refresh(["ghost"])
    assert fairplay.status("ghost") is None
    offline.clear()
    fairplay.refresh(["ghost"])
    assert offline == ["ghost"]        # tried again rather than cached as clean


def test_usernames_are_matched_case_insensitively(offline):
    fairplay.refresh(["Cheat"])
    assert fairplay.is_banned("CHEAT") and fairplay.is_banned("cheat")


def test_cheated_ids_and_flags_pick_out_the_right_games(offline):
    fairplay.refresh(["cheat", "honest"])
    games = [FakeGame("g1", "honest"), FakeGame("g2", "cheat")]
    assert fairplay.cheated_ids(games) == {"g2"}
    flags = fairplay.flags(games)
    assert set(flags) == {"g2"}
    assert flags["g2"]["flag"] == fairplay.FLAG
    assert "cheat" in flags["g2"]["note"]


def test_nothing_is_flagged_before_any_lookup():
    games = [FakeGame("g1", "cheat")]
    assert fairplay.cheated_ids(games) == set()
    assert fairplay.flags(games) == {}


def test_a_recent_opponent_is_rechecked_long_before_the_normal_ttl(offline):
    """Chess.com closes an account days to weeks after the games. An opponent
    from last week is exactly the one about to flip, so the week-long TTL would
    hide the ban for the whole window in which it actually arrives."""
    played = time.time() - 2 * 86400                 # played two days ago
    fairplay.refresh([("honest", played)])
    # a day later the normal TTL has nowhere near expired...
    store.kv_set("fairplay", "honest",
               {"status": "basic", "country": "PL", "checked": time.time() - 86400})
    offline.clear()
    fairplay.refresh(["honest"])                     # ...without recency: skipped
    assert offline == []
    fairplay.refresh([("honest", played)])           # ...with it: re-checked
    assert offline == ["honest"]


def test_an_old_opponent_keeps_the_cheap_ttl(offline):
    long_ago = time.time() - 200 * 86400
    fairplay.refresh([("honest", long_ago)])
    store.kv_set("fairplay", "honest",
               {"status": "basic", "country": "PL", "checked": time.time() - 2 * 86400})
    offline.clear()
    fairplay.refresh([("honest", long_ago)])
    assert offline == []                             # settled: no request
