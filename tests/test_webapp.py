"""Flask API: routes that don't require running the engine."""
from __future__ import annotations

import pytest

import webapp


@pytest.fixture
def client():
    webapp.app.config.update(TESTING=True)
    return webapp.app.test_client()


def test_config_endpoint(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.get_json()
    assert "game" in data["modes"]
    assert isinstance(data["depth"], int)
    assert "user" in data


def test_games_endpoint_returns_list(client):
    r = client.get("/api/games")
    assert r.status_code == 200
    games = r.get_json()
    assert isinstance(games, list)
    if games:                                   # depends on local PGN library
        g = games[0]
        for key in ("id", "white", "black", "result", "outcome", "time_class"):
            assert key in g


def test_compare_requires_two_players(client):
    r = client.get("/api/compare?a=onlyone")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_index_and_stylesheet(client):
    assert client.get("/").status_code == 200
    css = client.get("/style.css")
    assert css.status_code == 200
    assert "text/css" in css.content_type
    assert ".rv-svg" in css.get_data(as_text=True)


def test_flag_endpoint_round_trip(client, tmp_path, monkeypatch):
    from chessanalysis import overrides

    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    r = client.post("/api/flag?game=g9&flag=anomaly&note=opponent+disconnected")
    assert r.status_code == 200 and r.get_json()["flag"] == "anomaly"
    assert overrides.get_flag("g9")["note"] == "opponent disconnected"

    assert client.post("/api/flag?game=g9").get_json()["flag"] is None
    assert overrides.get_flag("g9") is None            # empty flag = unflag


def test_flag_endpoint_rejects_bad_input(client, tmp_path, monkeypatch):
    from chessanalysis import overrides

    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    assert client.post("/api/flag?flag=anomaly").status_code == 400   # no game
    assert client.post("/api/flag?game=g1&flag=nope").status_code == 400
    assert overrides.get_flag("g1") is None


def test_games_endpoint_marks_flagged(client, tmp_path, monkeypatch):
    from chessanalysis import overrides

    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    games = client.get("/api/games").get_json()
    if not games:
        pytest.skip("no local PGN library")
    gid = games[0]["id"]
    assert "flag" not in games[0]

    overrides.set_flag(gid, "anomaly", "opponent left")
    after = client.get("/api/games").get_json()
    row = next(g for g in after if g["id"] == gid)
    assert row["flag"] == "anomaly" and row["note"] == "opponent left"
    assert len(after) == len(games)          # still listed in the history


def test_error_wrapper_returns_json(client):
    # a bogus game selector raises inside the handler -> clean JSON error
    r = client.get("/api/game?selector=__definitely_no_such_game__&depth=6")
    assert r.status_code in (400, 500)
    assert "error" in r.get_json()


# --- syncing: every report pulls new games first ----------------------------

@pytest.fixture
def offline_sync(monkeypatch):
    """A sync that never touches the network; records who was scraped."""
    import scraper
    from chessanalysis import fairplay

    scraped = []

    def fake_scrape(user, *a, **k):
        scraped.append(user)
        return {"new": 2, "skipped": 1, "requests": 3}

    monkeypatch.setattr(scraper, "scrape", fake_scrape)
    monkeypatch.setattr(fairplay, "refresh",
                        lambda opponents, log=None: {"checked": 0, "banned": ["cheat"]})
    webapp._LAST_SYNC.clear()
    return scraped


def test_sync_reports_new_games_and_banned_opponents(client, offline_sync):
    d = client.post("/api/scrape?user=someone").get_json()
    assert d["new"] == 2 and d["banned"] == ["cheat"] and d["fresh"] is False
    assert offline_sync == ["someone"]


def test_repeat_sync_of_one_account_is_skipped(client, offline_sync):
    client.post("/api/scrape?user=someone")
    d = client.post("/api/scrape?user=SomeOne").get_json()   # case-insensitive
    assert d["fresh"] is True and d["requests"] == 0
    assert offline_sync == ["someone"]                       # not scraped twice


def test_force_bypasses_the_sync_throttle(client, offline_sync):
    client.post("/api/scrape?user=someone")
    assert client.post("/api/scrape?user=someone&force=1").get_json()["fresh"] is False
    assert offline_sync == ["someone", "someone"]


def test_sync_requires_a_username(client, offline_sync, monkeypatch):
    from chessanalysis import config

    monkeypatch.setattr(config, "get", lambda key, default=None: default)
    assert client.post("/api/scrape").status_code == 400


def test_game_review_follows_the_requested_account(client):
    """The username typed in the app bar reaches /api/game — before, it always
    reported on CHESS_USERNAME from .env."""
    r = client.get("/api/game?user=__no_such_player__&selector=last")
    assert r.status_code == 400
    assert "__no_such_player__" in r.get_json()["error"]
