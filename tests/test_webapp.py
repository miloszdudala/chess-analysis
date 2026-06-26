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


def test_error_wrapper_returns_json(client):
    # a bogus game selector raises inside the handler -> clean JSON error
    r = client.get("/api/game?selector=__definitely_no_such_game__&depth=6")
    assert r.status_code in (400, 500)
    assert "error" in r.get_json()
